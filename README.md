# RouteNex – Dynamic Logistic Routing & Fleet Coordination Hub

A complete full-stack capstone for multi-item commerce, on-demand rides, fleet operations and dynamic route optimization. It ships with five role-specific experiences, a relational data layer, live operational views, OpenAPI docs, ML prediction contracts and realistic Jaipur demo data.

## Project structure

```text
RouteNex/
├── frontend/       Responsive role-based SPA (HTML/CSS/JS)
├── backend/        FastAPI, auth/RBAC, APIs, optimizer, tests
├── database/       Relational schema, seed script, SQLite data
├── ml/             Training baseline and model documentation
├── docs/           Architecture, API and security notes
├── Dockerfile
├── docker-compose.yml
└── README.md
```

## Feature coverage

- **Customer:** service catalog, multi-item cart, quantities, saved addresses, checkout, cancellation and tracking.
- **Ride:** Jaipur location autocomplete, map-click pickup/drop, draggable markers, OpenStreetMap zoom, OSRM road routing, nearby-driver matching, traffic-aware fare/ETA and ride history.
- **Driver:** delivery assignments, ride jobs, vehicle context and status workflow APIs.
- **Dispatcher:** all orders, multi-order optimizer, route map, event alerts and dynamic rerouting.
- **Fleet manager:** vehicle/driver capacity, location, documents, availability, assignment and maintenance fields.
- **Admin:** users, orders, rides, vehicles, routes, optimizer output, alerts, costs/revenue, KPIs, analytics, audit and generated operational summaries.
- **Intelligence:** ETA, delay risk, demand forecast, fleet utilization and route-performance prediction endpoint.
- **Security:** PBKDF2 passwords, expiring signed tokens, RBAC, ownership checks, hashed expiring OTP, audit events and environment-based secrets.

## Exact Windows setup (PowerShell)

Prerequisite: Python 3.11+.

```powershell
# From the extracted RouteNex folder
cd RouteNex
Copy-Item backend\.env.example backend\.env

py -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r backend\requirements.txt

# Rebuild the complete Jaipur dataset (26 users, 38 orders, 12 vehicles,
# 12 drivers, 18 rides, 8 historical routes, alerts and analytics)
python database\seed.py --reset

# Start from backend so imports resolve
cd backend
$env:ROUTENEX_SECRET="replace-with-at-least-32-random-characters"
$env:ROUTENEX_DB="..\database\routenex.db"
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000**. API docs: **http://localhost:8000/docs**.

### Run tests on Windows

```powershell
cd RouteNex
.\.venv\Scripts\Activate.ps1
pytest backend\tests -q
```

### Docker alternative

```powershell
cd RouteNex
$env:ROUTENEX_SECRET="replace-with-at-least-32-random-characters"
docker compose up --build
```

## Demo sign-ins

| Role | Email | Password |
|---|---|---|
| Customer | customer@routenex.in | Demo@123 |
| Driver | driver@routenex.in | Demo@123 |
| Dispatcher | dispatcher@routenex.in | Demo@123 |
| Fleet manager | fleet@routenex.in | Demo@123 |
| Admin | admin@routenex.in | Demo@123 |

Mobile demo: **+91 8882846897**, OTP **123456**. This code applies only to the explicitly documented test number. Real OTP credentials are not hard-coded. Set up a provider adapter and secrets in environment variables before production.

Google demo mode creates a local test profile. For production, set `GOOGLE_CLIENT_ID` and replace the deliberately guarded demo branch with server-side Google ID-token verification.

## Production deployment notes

The application is fully runnable end-to-end with persisted relational operations. Interactive maps use OpenStreetMap tiles and the public OSRM route service, so map tiles and road routing require internet access; a distance fallback remains available if routing is temporarily unavailable. Before internet-scale deployment, move SQLite to PostgreSQL, use managed secrets/KMS, HTTPS, a real SMS provider, verified Google OAuth, Redis-backed rate limiting and queues, object storage for actual document uploads, WebSocket/GPS ingestion, and managed tile/geocoding/routing providers with appropriate usage plans. These boundaries are documented and the current API contracts are ready for those adapters.

See [architecture](docs/ARCHITECTURE.md), [API notes](docs/API.md), [UI system](docs/UI_SYSTEM.md), and [security checklist](docs/SECURITY.md).