# RouteNex - Phase 4 (trained ML models) - includes the Phase 3.1 hotfix

## Apply
Copy over your project (keep `frontend/assets/`, `database/seed.py`, `.env`):
`backend/` (whole folder), `frontend/` (all files), `ml/` (whole folder, replaces the old train.py), `database/schema.sql`, `start.bat`, `.gitignore`.
Then double-click `start.bat`. The first start downloads scikit-learn (about 60 MB, needs internet), then trains the models in the background (about 10 s).
Open Analytics & ML as admin; press Ctrl+Shift+R once. Tests: `pytest backend\tests -q`.

## What the models do (not just a dashboard)
- **ETA model**: the ETA shown when booking a ride or parcel now comes from the model, with reasons ("Heavy traffic +4 min", "Rain +2 min") and an "AI ETA" tag.
- **Delay-risk model**: every stop in an optimizer plan gets a delay-risk %, saved with the route; Analytics lists the riskiest live stops.
- **Demand model**: 24 h forecast by area, "Busy areas soon" card on the Driver Console, and a small (max +-10%) surge nudge.
- **Live weather** (Open-Meteo, free): rain feeds the ETA and demand models. Offline -> clear weather assumed.
- **Safe by design**: temporal validation, baselines, quality gates (a worse model is rejected and the previous one stays), graceful fallback to formulas if scikit-learn is missing.

## Be upfront in the viva
- Training data is **synthetic** (`ml/data.py`): no public per-trip dataset exists for Jaipur. The metrics show the pipeline works and beats the baselines on held-out days; they do NOT claim real-world accuracy. Real data plugs in at `data.load_real()`.
- Known limits: the optimizer's own timing still uses the speed model (ETA model is used for customer-facing ETAs); the demand index is relative (1.0 = typical hour).
