let csrfToken = '';
export function setCsrf(token) { csrfToken = token || ''; }
export function getCsrf() { return csrfToken; }

export class ApiError extends Error {
  constructor(message, status, data) { super(message); this.status = status; this.data = data; }
}

export async function api(path, { method = 'GET', body, headers = {}, retry = true } = {}) {
  const opts = { method, credentials: 'include', headers: { ...headers } };
  if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
  if (!['GET', 'HEAD'].includes(method) && csrfToken) opts.headers['X-CSRF-Token'] = csrfToken;
  const response = await fetch(`/api${path}`, opts);
  let data = null;
  try { data = await response.json(); } catch { /* empty response */ }
  if (!response.ok) {
    if (response.status === 403 && retry && String(data?.detail || '').includes('Security token')) {
      const me = await api('/auth/me', { retry: false });
      setCsrf(me.csrf_token);
      return api(path, { method, body, headers, retry: false });
    }
    const detail = typeof data?.detail === 'string' ? data.detail : 'Request failed. Please try again';
    throw new ApiError(detail, response.status, data);
  }
  return data;
}

export const money = (value) => `₹${Number(value || 0).toLocaleString('en-IN', { minimumFractionDigits: 0, maximumFractionDigits: 2 })}`;
export const dateTime = (value) => value ? new Date(value).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }) : '—';
export const titleCase = (value = '') => value.replaceAll('_', ' ').replace(/\b\w/g, c => c.toUpperCase());
export const uuid = () => crypto.randomUUID();
