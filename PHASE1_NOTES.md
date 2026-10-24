# RouteNex - Phase 1 (installable phone app + frontend hardening)

## Apply
Copy over your project (keep your `frontend/assets/`, `database/seed.py`, `ml/`, `docs/`):
`frontend/` (index.html, app.js, styles.css, pwa.js, sw.js, manifest.webmanifest, icons/), `backend/app.py`, `backend/tests/test_pwa.py`, `demo.ps1`.
Phase 0 must already be applied.

## Run the demo (laptop + Android phone)
1. One time:  `winget install --id Cloudflare.cloudflared`  (free, no account), then reopen PowerShell.
2. From the RouteNex folder:  `.\demo.ps1`   (if blocked: `Set-ExecutionPolicy -Scope Process Bypass`)
3. Copy the `https://xxxx.trycloudflare.com` link it prints -> open in **Chrome on the phone** -> tap **Install RouteNex app** (or menu ⋮ > Install app).
   The link changes every run, so do this once before the class starts. If class Wi-Fi blocks it, connect the laptop to your phone's hotspot.
4. Laptop must stay on and running during the demo. Test: `pytest backend\tests -q`

## What changed
- PWA: manifest, icons (incl. maskable), service worker, install button, offline banner. API calls are never cached.
- Phone layout: bottom navigation bar, 44px tap targets, no zoom-on-focus, safe-area padding, tables scroll inside cards.
- Security: all API data is HTML-escaped before display (stored-XSS fix); inline onclick handlers removed; Content-Security-Policy added; expired tokens dropped at startup.
- Honest data: ops map draws real routes/vehicles/orders from the API; fake "92% on-time" replaced by real route-completion %.

## Known limits (next phases)
Ride "nearby drivers" dots are still demo markers (Phase 2 adds a real endpoint). Token stays in localStorage (acceptable once XSS is closed; cookie auth can come later). Leaflet loads from unpkg without SRI.
