# Architecture

RouteNex v3 is a modular monolith: one FastAPI application, one PostgreSQL database, one React SPA,
and a lightweight background worker. It is designed to be honest about money, state and identity.

## Request path
```
Browser (React SPA, cookie session + CSRF header)
  → TrustedHost + CORS + security/CSP middleware + request-id + body cap
  → FastAPI router (strict Pydantic input, role dependency)
  → Service layer (transactions, row locks, advisory locks)
  → PostgreSQL (CHECK/FK/partial-unique constraints, Alembic migrations)
```

## Layers
- **api/** holds HTTP concerns only: auth dependencies, query/body validation, serializers.
- **services/** holds business rules: pricing, payments, trips, orders, dispatch, catalog, places,
  routing, coupons, weather, ML serving and the assistant. Services receive a SQLAlchemy `Session`
  and commit through the request lifecycle (`get_db`) or `session_scope()` in the worker.
- **core/** holds configuration (fail-closed production validation), security (argon2id, opaque
  hashed sessions, CSRF, encrypted proof codes) and PostgreSQL-backed rate limits.
- **models.py** defines 30 tables. Invariants are enforced in the database, not only in Python:
  non-negative wallets, valid status enums, positive money, unique active vehicle/driver assignments,
  idempotency keys, webhook dedup and coupon-reference uniqueness.

## Key flows
- **Checkout**: lock user → idempotency lookup → lock products → decrement stock (reserve for
  prepaid) → evaluate coupon under lock → create order/items → record wallet/cash tender → clear cart.
- **Prepaid capture**: provider order created server-side; capture re-fetches/verifies; fulfillment
  only transitions `awaiting_payment` references; late capture after expiry auto-refunds.
- **Trips**: signed user-bound quote → atomic create → eligible-driver matching under advisory lock
  → proof-code arrive/start/complete → cash settled on completion → 80/20 driver earning.
- **Dispatch**: advisory-locked preview builds an immutable `RoutePlan` with a `state_hash`;
  apply re-checks the snapshot and creates exactly the previewed routes/stops, or rejects as stale.
- **Worker**: expires abandoned reservations/searches, runs demo autopilot (development only), and
  executes queued ML training jobs.

## Frontend
React 19 + Vite. Role-guarded routes, a shared API client with automatic CSRF refresh, server-backed
cart/notifications, Leaflet maps, and a payment modal that branches between demo and Razorpay.
The service worker caches only the shell and static assets — never API responses.

## ML
`ml/train.py` trains candidates, compares them against the incumbent using explicit gates
(ETA MAE improvement/R², delay AUC), and atomically promotes only passing artifacts into
`registry.json`. `mlserve` serves **only promoted** entries; the dashboard never shows rejected
candidates as live models.

## Data lifecycle
Alembic is the only schema authority (`0001` → `0002`). The app refuses to start unless the database
is at head. `scripts/bootstrap.py` is idempotent and append-only; it never deletes operational data.
`scripts/migrate_sqlite.py` imports v2 data transactionally into a fresh v3 database.
