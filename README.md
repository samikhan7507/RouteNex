# RouteNex

**Local commerce, rides, parcels and fleet operations for Jaipur — rebuilt as a production-shaped v3.**

RouteNex is one account for everyday essentials: shop a local catalogue, book a ride or send a parcel,
pay by wallet/cash/UPI-card, and follow every handover with proof codes. Dispatchers plan immutable
routes, drivers complete proof-verified work, fleet managers keep vehicles healthy, and admins see
who is signed in, what changed and where money moved.

> v3 replaces the earlier SQLite/demo monolith. Money is integer **paise**, timestamps are
> timezone-aware, sessions are database-backed and revocable, and production configuration
> **fails closed** instead of silently seeding demo accounts.

---

## What works

| Area | Highlights |
|---|---|
| **Shop** | 190-product catalogue with real photos, server-side cart, coupons, stock reservations, COD/wallet/prepaid checkout, idempotent orders, proof-of-delivery |
| **Rides & parcels** | Named place autocomplete, signed 5-minute fare quotes, transparent vehicle classes, driver matching, encrypted pickup/delivery codes, ratings, automatic refunds |
| **Payments** | Wallet ledger, cash settled only on completion, Razorpay order/capture/verify/webhook flow, demo provider for local testing, webhook dedup, late-capture auto-refund |
| **Operations** | Preview == apply route optimizer, stale-plan rejection, vehicle/driver double-booking protection, alerts, events, analytics |
| **Fleet** | Vehicles, drivers, maintenance, breakdown handling |
| **Admin** | Active sessions, users/roles, login history, audit trail, payments/refunds, catalogue, driver settlements |
| **ML** | ETA/delay/demand models with **gated promotion** — only approved registry artifacts are served |
| **PWA** | Installable React SPA, offline shell/static assets only; API responses are never cached |

## Architecture

```
backend/app/
  api/          FastAPI routers (auth, shop, trips, payments, wallet, places, driver, fleet, ops, admin, ml)
  core/         settings, security (argon2id + sessions + CSRF), rate limits
  services/     pricing, payments, trips, orders, dispatch, catalog, places, routing, coupons, weather, mlserve, assistant
  models.py     30 PostgreSQL tables with CHECK/FK/partial-unique constraints
  schemas.py    strict, extra-forbid input models
  main.py       security middleware, request IDs, health/ready, SPA fallback
frontend/       React 19 + Vite SPA (role-guarded routes, Leaflet maps, payment modal, assistant)
migrations/     Alembic 0001 → 0002
ml/             data/features/train + gated artifact registry
scripts/        dev_db, bootstrap, worker, migrate_sqlite
```

The API serves the built SPA from `frontend/dist`. In development you can also run Vite on `:5173`
with `/api` proxied to `:8000`.

---

## Quickstart (local demo)

Requires **Python 3.11+**, **Node 22+**, and Linux/macOS for the optional embedded PostgreSQL.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements-dev.txt

# Terminal 1 — embedded PostgreSQL (keep it running)
python scripts/dev_db.py --init --write-env

# Terminal 2 — schema, demo data, SPA build, API
alembic upgrade head
python scripts/bootstrap.py --demo
(cd frontend && npm ci && npm run build)
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000 --reload

# Optional terminal 3 — background worker (reservation expiry, demo autopilot, training jobs)
python scripts/worker.py
```

The API serves the built SPA from `frontend/dist`; rebuild after changing frontend source.

Open **http://localhost:8000**. For hot-reload frontend development run `npm run dev` and open
**http://localhost:5173** instead.

### Demo accounts (development only)

| Role | Email | Password |
|---|---|---|
| Admin | `samikhan@gmail.com` | `sami@123` |
| Customer | `customer@routenex.in` | `Demo@123` |
| Driver | `driver@routenex.in` | `Demo@123` |
| Dispatcher | `dispatcher@routenex.in` | `Demo@123` |
| Fleet manager | `fleet@routenex.in` | `Demo@123` |

Demo phone OTP: `+919876543210` → code `123456`. Payments use the **demo** provider (simulate
success/failure). These shortcuts are refused when `APP_ENV=production|staging`.

---

## Configuration

Copy `.env.example` to `.env`. Important variables:

- `DATABASE_URL` — PostgreSQL only (no SQLite runtime fallback).
- `SECRET_KEY` — 32+ random characters; **required** in production/staging.
- `APP_ENV`, `BASE_URL` — production requires HTTPS.
- `DEMO_MODE`, `DEMO_AUTOPILOT`, `SEED_DEMO_DATA` — must all be `false` in production/staging.
- `PAYMENT_PROVIDER=razorpay` + `RAZORPAY_KEY_ID/KEY_SECRET/WEBHOOK_SECRET` in production.
- `OTP_PROVIDER=twilio` + Twilio credentials in production.
- `ADMIN_EMAIL` / `ADMIN_PASSWORD` — unique, non-demo password required in production.
- `LOCATION_PROVIDER`, `ROUTING_URL`, `TILE_URL`, `WEATHER_ENABLED` — maps/routing/weather.
- `CORS_ORIGINS`, `TRUSTED_HOSTS` — browser allowlists (no wildcard credentialed CORS).

See [docs/SECURITY.md](docs/SECURITY.md) for the full threat model and guarantees.

## Docker (production template)

```bash
cp .env.example .env       # fill POSTGRES_PASSWORD, SECRET_KEY, BASE_URL, ADMIN_*, Razorpay, Twilio…
docker compose up --build
```

The image builds the SPA, runs `alembic upgrade head`, bootstraps **only the configured admin**
(never demo data in production), then starts Uvicorn. A separate `worker` service runs background
jobs. The compose file fails fast if required secrets are missing.

For a containerised *demo*, set `APP_ENV=development DEMO_MODE=true PAYMENT_PROVIDER=demo
OTP_PROVIDER=console` in `.env` and run `python scripts/bootstrap.py --demo` against the compose DB.

---

## Tests & checks

```bash
pytest -q                                   # 37 PostgreSQL-backed API/unit tests (uses routenex_test)
ruff check backend/app scripts migrations ml backend/tests/v3
cd frontend && npm test                     # Vitest unit tests
cd frontend && npm run build                # production SPA build
cd frontend && npm run test:e2e             # real Chromium E2E against a running demo API
python tools/preflight.py                   # pre-demo smoke check (stdlib only)
```

CI (`.github/workflows/ci.yml`) runs lint + Alembic + pytest on PostgreSQL 16, then builds the SPA,
runs Vitest, bootstraps a demo DB and exercises the browser E2E flow.

## Migrating from v2 (SQLite)

`scripts/migrate_sqlite.py` is a **one-way, transactional, dry-run-by-default** importer. The target
must be a fresh PostgreSQL database at Alembic head (run it *before* `bootstrap.py`).

```bash
alembic upgrade head
python scripts/migrate_sqlite.py --source /path/to/legacy-routenex.db            # dry-run report
python scripts/migrate_sqlite.py --source /path/to/legacy-routenex.db --apply    # import
python scripts/bootstrap.py                                                    # ensure admin
```

It converts rupees → paise, normalises delivery windows to IST, rotates legacy plaintext handover
OTPs into encrypted 6-digit codes, preserves ledger/audit history, and refuses double-booked active
routes/drivers. See [docs/MIGRATION.md](docs/MIGRATION.md).

## API docs

Interactive OpenAPI docs are available at **`/docs`** in development/test only (disabled in
production). A concise endpoint map lives in [docs/API.md](docs/API.md).

## Project notes

- Optimized illustrative Pexels category photos are included; source/license credits are in
  `frontend/public/products/credits.json`. Unused search thumbnails are not kept in the repository.
- E2E screenshots are written to ignored `.local/screenshots/` (override with `SCREENSHOT_DIR`).
- Maps use OpenStreetMap tiles; routing prefers OSRM and falls back to a clearly labelled estimate.
- The assistant proposes actions but **never executes them without explicit confirmation**.
- ML candidates are promoted only when they beat the incumbent by the configured gates.
