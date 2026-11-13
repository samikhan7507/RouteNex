import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, getCsrf, money, setCsrf, titleCase, uuid } from './api';

const response = (status, data) => ({ ok: status >= 200 && status < 300, status, json: async () => data });

beforeEach(() => { setCsrf(''); vi.restoreAllMocks(); });
afterEach(() => { vi.unstubAllGlobals(); });

describe('formatters', () => {
  it('formats rupees for en-IN', () => {
    expect(money(1234.5)).toContain('₹');
    expect(money(1234.5)).toContain('1,234');
    expect(money(null)).toBe('₹0');
  });
  it('title-cases snake_case statuses', () => {
    expect(titleCase('out_for_delivery')).toBe('Out For Delivery');
    expect(titleCase('')).toBe('');
  });
  it('generates unique idempotency keys', () => {
    expect(uuid()).toMatch(/^[0-9a-f-]{36}$/);
    expect(uuid()).not.toBe(uuid());
  });
});

describe('api client', () => {
  it('sends cookies and CSRF only on mutations', async () => {
    const fetch = vi.fn(async () => response(200, { ok: true }));
    vi.stubGlobal('fetch', fetch);
    setCsrf('token-123');
    await api('/auth/me');
    expect(fetch.mock.calls[0][1].headers['X-CSRF-Token']).toBeUndefined();
    expect(fetch.mock.calls[0][1].credentials).toBe('include');
    await api('/orders', { method: 'POST', body: { a: 1 } });
    const opts = fetch.mock.calls[1][1];
    expect(opts.headers['X-CSRF-Token']).toBe('token-123');
    expect(opts.headers['Content-Type']).toBe('application/json');
    expect(opts.body).toBe('{"a":1}');
  });

  it('throws ApiError with the server detail', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response(409, { detail: 'Insufficient stock' })));
    await expect(api('/orders', { method: 'POST', body: {} })).rejects.toMatchObject({ status: 409, message: 'Insufficient stock' });
    await expect(api('/orders', { method: 'POST', body: {} })).rejects.toBeInstanceOf(ApiError);
  });

  it('refreshes an expired CSRF token once and retries the mutation', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(response(403, { detail: 'Security token missing or expired. Refresh and try again' }))
      .mockResolvedValueOnce(response(200, { csrf_token: 'fresh-token' }))
      .mockResolvedValueOnce(response(200, { ok: true }));
    vi.stubGlobal('fetch', fetch);
    setCsrf('stale');
    const result = await api('/orders', { method: 'POST', body: { x: 1 } });
    expect(result).toEqual({ ok: true });
    expect(getCsrf()).toBe('fresh-token');
    expect(fetch).toHaveBeenCalledTimes(3);
    expect(fetch.mock.calls[1][0]).toBe('/api/auth/me');
    expect(fetch.mock.calls[2][1].headers['X-CSRF-Token']).toBe('fresh-token');
  });
});
