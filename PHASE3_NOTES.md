# RouteNex - Phase 3 (real route optimizer + driver route) and Phase 2 fixes

## Apply
Copy over your project (keep `frontend/assets/`, `database/seed.py`, `ml/`, `docs/`, your `.env`):
`backend/` (whole folder), `frontend/` (all files), `database/schema.sql`.
Start with `start.bat`, then press Ctrl+Shift+R once. Tests: `pytest backend\tests -q` (44 tests).
Your database upgrades itself on start (item and order weights are filled in automatically).

## Fixes from your screenshots
- "You already have an active ride": old trips nobody finished now expire automatically (and refund + free the driver). A banner on the booking screen also links to the active ride.
- My Trips: icons no longer stretch into wide bars. Wallet times now show in your local time.
- Cab "no driver nearby" label now shows the real pickup time when a cab can still be matched.
- Drivers get their delivery route back: **My Route** page (stops, ETAs, cash to collect, Picked up / Out for delivery / Delivered / Failed).

## Optimizer (Optimizer page for admin, dispatcher, fleet manager)
- Real order weights vs vehicle capacity (a 300 kg move can no longer be put on a 20 kg bike).
- Delivery windows are read from the order text. Overdue windows are served first; windows opening 2+ hours later wait for a later plan.
- Real road distances from OSRM when online, estimated distances offline (the page tells you which one was used).
- Method: priority-ordered cheapest insertion, then local search (2-opt, relocate, swap) minimising distance cost + lateness + unplanned-order penalties.
- **Preview** shows the plan without saving; **Apply** creates routes. Every plan shows Old method vs Optimizer (distance, late minutes, cost, vehicles).
- Orders that cannot be planned are listed with the reason (too heavy, no capacity, window later).
- Breakdown (Reroute) now re-plans the released orders automatically.

## Demo flow
1. Admin -> Optimizer -> Preview plan -> read the comparison -> Apply plan.
2. Note a vehicle plate in the result, log in as its driver (password Demo@123):
   101 driver@ · 102 driver2@ · 201 driver3@ · 202 driver4@ · 203 driver5@ · 301 driver6@ · 302 driver7@ · 401 driver8@ · 501 driver9@ · 601 driver11@ · 701 driver12@  (all @routenex.in)
3. Driver -> My Route -> step through the stops. The route completes by itself when the last stop is done.
4. Admin -> Fleet -> mark that vehicle as broken down (or use Routes/Alerts reroute) -> orders are re-planned automatically.

## Be upfront in the viva
- Solver is my own heuristic (no OR-Tools), so it is fast and explainable, but not guaranteed optimal. The "Old method" row is the previous nearest-neighbour planner on the same distances; it ignores time windows, so most of the cost gain comes from avoiding lateness. Distance saving is shown separately.
- Positions on the map for planned routes are straight lines between stops; ETAs use road distances only when OSRM answered.
