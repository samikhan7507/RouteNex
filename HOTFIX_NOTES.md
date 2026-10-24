# RouteNex Phase 1.1 hotfix
Copy over your project: `frontend/sw.js`, `frontend/app.js`, `backend/app.py`, `database/create_admin.py`.
1. Maps: tiles/marker icons were blocked by the service worker's own CSP (my bug). Fixed; "Loading map..." text no longer stays behind the map.
   After copying: restart uvicorn, open the site, press Ctrl+Shift+R once (loads the new service worker v2).
2. Your admin login:  python database\create_admin.py --name "Sami Khan" --email samikhan75706@gmail.com --retire-demo-admin
   (type the password at the prompt; re-run after any `seed.py --reset`).
