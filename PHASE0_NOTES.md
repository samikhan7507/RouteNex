# RouteNex - Phase 0 (audit fixes + restructure)

## How to apply (Windows, PowerShell, from your RouteNex folder)
1. Back up your project. Copy this zip's `backend/`, `database/schema.sql`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.gitignore` over yours.
   Keep your own `database/seed.py`, `frontend/`, `ml/`, `docs/` (unchanged in this phase).
2. `Copy-Item backend\.env.example backend\.env`  (now really loaded) and set ROUTENEX_SECRET.
3. `pip install -r backend\requirements-dev.txt`
4. `python database\seed.py --reset`
5. `pytest backend\tests -q`   <- please send me the output
6. `cd backend; uvicorn app:app --reload`

## What changed
Security: Google-demo admin takeover closed - server-side fare/ETA (client values are hints only) - ownership checks on rides/orders/routes/vehicles/drivers - rate limits on login/OTP - keyed OTP hash, OTP attempts limited, old codes invalidated, demo OTP only when DEMO_MODE - weak-secret guard in production - security headers - driver license no longer sent to riders.
Correctness: atomic stock (no overselling) - cart duplicates merged - cancel restocks and releases route - order/ride status state machines - route auto-completes and frees driver+vehicle - atomic driver claim (no double booking) - re-optimizing after a breakdown no longer hits a UNIQUE-constraint crash - optimizer ETAs are cumulative per stop and savings are measured against arrival order - readable validation errors.
Structure: config.py, db.py (tx), deps.py, schemas.py, routers/, services/, tests/ (15 tests), schema indexes, Dockerfile (auto-seeds, PORT-aware), .dockerignore.

## Not in Phase 0 (on purpose)
Frontend XSS escaping + token storage, PWA + hosting (Phase 1). Optimizer is still greedy (Phase 3). /api/ml/predictions is labelled `placeholder-baseline` (Phase 4).
