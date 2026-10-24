# RouteNex architecture

```text
Browser SPA ── HTTPS/Bearer JWT ── FastAPI service ── SQLite (demo)
                                     ├─ optimizer
                                     ├─ RBAC/audit
                                     └─ ML inference contract
```

The frontend is a dependency-free responsive SPA, served by the API to avoid cross-origin deployment issues. The API uses layered security helpers, typed request validation, relational constraints, transactions, role guards and audit events. SQLite is ideal for a one-command capstone; migrate to PostgreSQL by replacing `db.py` with a connection pool/repository while preserving endpoints.

## Roles
Customer: catalog, cart, addresses, orders, tracking and rides. Driver: assignments, ride jobs and vehicle. Dispatcher: global orders, route optimization, incidents and rerouting. Fleet manager: assets, drivers, documents and maintenance. Admin: all KPIs, users, audit and analytics.

## Optimizer
The deterministic baseline batches pending orders, filters available driver/vehicle pairs, enforces approximate capacity, prioritizes urgent orders, creates nearest-neighbour stop sequences, calculates distance/duration/cost and persists routes and assignments. Incident events release affected orders and flag routes for re-optimization. A production upgrade can swap in OR-Tools without changing the API contract.

## Maps
The included offline map visualizes routes without API keys. Production can wire Google Maps/Mapbox via environment keys; coordinate fields and route geometry already follow that contract.