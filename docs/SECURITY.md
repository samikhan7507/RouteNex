# Security model

## Identity & sessions
- Passwords hashed with **argon2id**; legacy PBKDF2 hashes are verified and transparently rehashed on
  successful login. A dummy hash equalises timing for unknown accounts.
- Browser sessions are **opaque random tokens**, stored only as SHA-256 hashes in `user_sessions`,
  with expiry, idle timeout, revocation, IP/user-agent and login-event history.
- Session cookie is `HttpOnly`, `SameSite=Lax`, and `Secure` in production/staging. No auth tokens are
  placed in `localStorage`.
- Every mutation requires a per-session **CSRF token** (hashed at rest) and an allowed `Origin`.
  Same-origin SPA calls work on localhost and proxied previews without wildcard credentialed CORS.
- Admins can see and revoke active sessions; users can revoke their own other devices.

## Authorization
- Role dependencies guard every sensitive router (`customer`, `driver`, `dispatcher`,
  `fleet_manager`, `admin`). Object ownership is checked in queries/locks, not trusted from the client.
- Drivers can only act on trips assigned to them; customers only see their own orders/trips/OTPs.

## Money & state integrity
- All money is integer **paise**; inputs reject more than two decimal places.
- Driver net is `gross_paise * 80 // 100`: fractional paise are truncated from net and retained in
  the platform fee, so `gross = net + fee` exactly. Tests pin this boundary rather than rounding floats.
- Wallet changes are ledger entries under a user row lock; balances have a non-negative CHECK.
- Lock order is documented and consistent (User → Payment → Order/Trip/Product) to avoid deadlocks.
- Orders/trips/checkouts require **idempotency keys**; replays return the original result.
- Stock is reserved for prepaid checkout and released on failure/expiry; coupons are evaluated under
  `FOR UPDATE` with a unique coupon-reference constraint.
- Cash is settled **only on completed handover**. Refunds go to the original method; cash refunds
  require an explicit `cash_returned` confirmation.
- Razorpay orders are created server-side; capture re-fetches provider state; signatures are verified;
  webhooks are HMAC-checked and deduplicated; late captures after expiry are auto-refunded.

## Handover proofs
- Pickup/delivery codes are 6-digit, hashed (SHA-256) for verification and encrypted (Fernet) for
  authorised display. Proof attempts are rate-limited. Demo codes are only exposed in demo mode.

## Dispatch safety
- Route previews are immutable and snapshotted (`state_hash`, 10-minute expiry). Apply is exact or
  rejected as stale. Partial unique indexes prevent double-booking active vehicles/drivers.

## HTTP hardening
- TrustedHost allowlist, explicit CORS origins, CSP (`default-src 'self'`, Razorpay script/frame,
  OSM tiles), `nosniff`, `Referrer-Policy`, `Permissions-Policy`, `X-Frame-Options: DENY`,
  `frame-ancestors 'none'`, HSTS in production, request IDs, and a ~1.1 MB body cap.
- PostgreSQL-backed rate limits survive restarts and are shared across workers; successful limits are
  committed so a later error cannot reset an attacker's counter.
- OpenAPI docs are disabled in production/staging.

## Configuration fail-closed
Production/staging refuses to start unless: a 32+ char `SECRET_KEY`, HTTPS `BASE_URL`, all demo flags
false, Razorpay provider + credentials, a real OTP provider, and a unique non-demo admin password are
set. Demo seeding/autopilot are development-only.

## Secrets handling
`.env` is git-ignored and chmod 600 by the dev DB helper. Never commit real credentials; use
`.env.example` as the template. Product photo credits are recorded; no premium/watermarked stock is
bundled.
