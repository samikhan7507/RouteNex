# RouteNex - Phase 2 (product flows)

## Apply
Copy over your project (keep `frontend/assets/`, `database/seed.py`, `ml/`, `docs/`, your `.env`):
`backend/` (whole folder), `frontend/` (all files), `database/schema.sql`.
Your database is upgraded automatically on start (new columns/tables are added, nothing is deleted).
Then: `pytest backend\tests -q` and double-click `start.bat`.

## New for customers
- Home: Ride / Parcel / Shop tiles, active trips, offers, wallet.
- Ride: Bike / Auto / Cab with live fares, demand multiplier, nearby driver counts, coupon, payment method, start OTP.
- Parcel: weight, size, fragile, recipient; pickup OTP + delivery OTP; price by weight and distance.
- Live tracking: driver moves along the road, ETA, status steps, call driver, cancel (fee after driver arrives), rating.
- Wallet (ledger, demo top-up, refunds), coupons (WELCOME50, RIDE20, PARCEL25, SHOP100), checkout with real address picker.
- My Trips: rides + parcels + orders in one list with working search and filters.
## Drivers / admin
- Driver console: online/offline, current job with arrive / OTP start / OTP delivery, earnings (80% share), history.
- Admin: activate / deactivate users.
## Demo notes (be upfront in the viva)
- Drivers are simulated: DEMO_AUTOPILOT=true makes demo trips arrive, start and finish by themselves.
  Set DEMO_AUTOPILOT=false in backend\.env and log in as a driver (ridedriver1@routenex.in / Demo@123, or driver@routenex.in) to drive a trip manually with the OTPs.
- UPI and card payments are mocked (no money moves). Wallet and refunds are a real ledger.
- Demo fleet (12 Bike/Auto/Cab drivers) and Rs 500 wallet credit for demo customers are added at startup in demo mode only.
