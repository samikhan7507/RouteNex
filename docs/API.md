# RouteNex v3 API

Base URL: `/api`. Interactive OpenAPI: `/docs` (development/test only). All mutations require a
valid session cookie **and** `X-CSRF-Token`. Responses are JSON; errors use `{"detail": "..."}`
with appropriate 4xx/5xx status and an `X-Request-ID` header.

## Public / health
| Method | Path | Notes |
|---|---|---|
| GET | `/health` | liveness + version |
| GET | `/ready` | PostgreSQL + Alembic head readiness |
| GET | `/auth/config` | demo mode, payment/location/OTP provider flags; public demo account emails/password only when demo mode is on |
| POST | `/auth/register`, `/auth/login` | email/password; sets opaque session cookie |
| POST | `/auth/otp/request`, `/auth/otp/verify` | phone OTP (demo phone in development) |
| POST | `/auth/google` | optional Google Identity credential |
| GET | `/places/search?q=` | named place autocomplete (local/photon/geoapify) |
| GET | `/products`, `/products/{id}`, `/categories` | catalogue |

## Account
`GET/PATCH /auth/me`, `POST /auth/change-password`, `POST /auth/logout`,
`GET /auth/sessions`, `DELETE /auth/sessions/{id}`,
`GET/POST /addresses`, `DELETE /addresses/{id}`,
`GET /notifications`, `POST /notifications/{id}/read`.

## Shop (customer/admin)
`GET/PUT/DELETE /cart`, `POST /orders` (idempotent checkout from server cart),
`GET /orders`, `GET /orders/{id}`, `POST /orders/{id}/cancel`,
`POST /orders/{id}/status?status=picked_up|out_for_delivery|delivered|failed&reason=`
(driver/dispatcher/admin; delivery requires the 6-digit proof code).

## Rides & parcels
`POST /trips/quote` → signed `quote_token` (300 s, user-bound),
`POST /trips` (idempotent), `GET /trips`, `GET /trips/{id}`,
`POST /trips/{id}/cancel`, `POST /trips/{id}/rate`, `GET /drivers/nearby`.

## Driver workspace
`GET/PATCH /driver/me`, `GET /driver/requests`, `POST /driver/requests/{trip_id}/accept`,
`GET /driver/trips`, `POST /driver/trips/{id}/{arrive|start|complete}` (proof codes),
`GET /driver/earnings`.

## Payments & wallet
`POST /payments/checkout`, `GET /payments`, `GET /payments/{public_id}`,
`POST /payments/verify` (Razorpay signature), `POST /payments/{public_id}/demo` (demo only),
`POST /payments/{public_id}/refund` (admin; cash refunds require `cash_returned=true`),
`POST /payments/webhooks/razorpay` (signature-verified, deduplicated),
`GET /wallet`, `POST /wallet/topup`, `GET /coupons`, `POST /coupons/validate`.

## Operations (dispatcher/fleet_manager/admin)
`POST /optimizer/preview`, `POST /optimizer/apply` (immutable plan, stale-state rejection),
`GET /optimizer/summary`, `GET /routes`, `GET /alerts`, `POST /alerts/{id}/ack`,
`POST /events`, `GET /analytics`.

## Fleet (fleet_manager/admin)
`GET/POST /vehicles`, `PATCH /vehicles/{id}/status`, `GET/POST /drivers`,
`GET/POST /maintenance`.

## Admin
`GET /admin/overview`, `GET /admin/users`, `PATCH /admin/users/{id}/active`,
`PATCH /admin/users/{id}/role`, `GET /admin/sessions`, `DELETE /admin/sessions/{id}`,
`GET /admin/login-events`, `GET /admin/audit`, `GET /admin/payments`,
`GET/POST /admin/products`, `PATCH /admin/products/{id}`,
`GET /admin/settlements`, `POST /admin/settlements/{id}/mark-paid`.

## ML & assistant
`GET /ml/status`, `GET /ml/forecast`, `POST /ml/train`, `GET /ml/jobs/{id}`,
`POST /assistant/message`, `POST /assistant/confirm`, `POST /assistant/dismiss`.
Assistant actions are proposed first and only run after explicit confirmation.

## Conventions
- Money is returned as rupees (float) **and** `*_paise` integers where useful; inputs accept at most
  two decimal places.
- Delivery windows must be timezone-aware ISO-8601, single-day, within the next 7 days.
- Idempotency keys are required for orders, trips and payment checkouts.
- List endpoints paginate with `page` / `page_size` where applicable.
