"""RouteNex v3 pre-demo check (standard library only).

Start the API first, then: python tools/preflight.py
Uses cookie sessions + CSRF exactly like the browser; never prints secrets.
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv("ROUTENEX_URL", "http://localhost:8000").rstrip("/")
RESULTS: list[str] = []


def say(level: str, name: str, detail: str = "", fix: str = ""):
    RESULTS.append(level)
    print(f"[{level:^4}] {name}" + (f" — {detail}" if detail else ""))
    if fix and level != "OK":
        print(f"        fix: {fix}")


class Client:
    def __init__(self):
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.csrf = ""

    def call(self, path, method="GET", body=None, headers=None, timeout=8):
        data = json.dumps(body).encode() if body is not None else None
        hdrs = {"Content-Type": "application/json", **(headers or {})}
        if method not in ("GET", "HEAD") and self.csrf:
            hdrs["X-CSRF-Token"] = self.csrf
        req = urllib.request.Request(BASE + path, method=method, data=data, headers=hdrs)
        with self.opener.open(req, timeout=timeout) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}, r.headers

    def login(self, email, password="Demo@123"):
        data, _ = self.call("/api/auth/login", "POST", {"email": email, "password": password})
        self.csrf = data.get("csrf_token", "")
        return data


def main():
    print(f"RouteNex v3 preflight against {BASE}\n")
    anon = Client()
    try:
        health, headers = anon.call("/api/health")
        ok = health.get("status") == "ok" and health.get("version", "").startswith("3.")
        say("OK" if ok else "FAIL", "API health", f"{health.get('service')} {health.get('version')}",
            "start uvicorn app.main:app --app-dir backend --port 8000")
        say("OK" if headers.get("X-Content-Type-Options") == "nosniff" else "WARN", "Security headers",
            "nosniff + CSP present" if headers.get("Content-Security-Policy") else "missing CSP")
        ready, _ = anon.call("/api/ready")
        say("OK" if ready.get("status") == "ready" else "FAIL", "Database readiness", str(ready),
            "run alembic upgrade head and check DATABASE_URL")
    except Exception as exc:
        say("FAIL", "API reachable", str(exc)[:100], "start the API and PostgreSQL first")
        return summary()

    try:
        html = urllib.request.urlopen(BASE + "/shop", timeout=8).read().decode("utf-8", "ignore")
        say("OK" if "RouteNex" in html else "FAIL", "React SPA served", "/shop returns the app shell",
            "run cd frontend && npm run build")
    except Exception as exc:
        say("FAIL", "React SPA served", str(exc)[:80], "run cd frontend && npm run build")

    clients = {}
    try:
        config, _ = anon.call("/api/auth/config")
        if not config.get("demo_mode"):
            say("FAIL", "Demo configuration", "DEMO_MODE is off",
                "use APP_ENV=development and DEMO_MODE=true for the public demo")
        accounts = config.get("demo_accounts") or []
        password = config.get("demo_password")
        if not accounts or not password:
            say("FAIL", "Demo accounts advertised", "no public demo credentials in /auth/config",
                "deploy the unified demo-account build")
        for account in accounts:
            role, email = account["role"], account["email"]
            c = Client()
            try:
                result = c.login(email, password)
                user = result.get("user", {})
                ok = user.get("email") == email and user.get("role") == role
                say("OK" if ok else "FAIL", f"Login: {role}", user.get("email", email),
                    "run python scripts/bootstrap.py --demo (development only)")
                if ok:
                    clients[role] = c
            except Exception as exc:
                say("FAIL", f"Login: {role}", str(exc)[:80],
                    "set SEED_DEMO_DATA=true and redeploy, or run python scripts/bootstrap.py --demo")
    except Exception as exc:
        say("FAIL", "Demo configuration", str(exc)[:100], "check /api/auth/config")

    if "customer" in clients:
        c = clients["customer"]
        try:
            products, _ = c.call("/api/products?page_size=1")
            total = products.get("total", 0)
            say("OK" if total >= 50 else "WARN", "Catalogue", f"{total} products",
                "run python scripts/bootstrap.py --catalog")
            places, _ = c.call("/api/places/search?q=mal")
            say("OK" if places.get("results") else "WARN", "Place search", f"{len(places.get('results', []))} results for 'mal'")
            wallet, _ = c.call("/api/wallet")
            say("OK", "Wallet", f"₹{wallet.get('balance', 0):.2f}")
            quote, _ = c.call("/api/trips/quote", "POST", {"kind": "ride",
                "pickup": {"name": "Malviya Nagar", "lat": 26.854, "lng": 75.8243},
                "drop": {"name": "Vaishali Nagar", "lat": 26.9126, "lng": 75.7442}})
            say("OK" if quote.get("quotes") else "WARN", "Fare quote", f"{len(quote.get('quotes', []))} vehicle classes")
        except Exception as exc:
            say("FAIL", "Customer flow", str(exc)[:100])

    if "driver" in clients:
        try:
            d, _ = clients["driver"].call("/api/driver/me")
            say("OK" if d.get("id") else "FAIL", "Driver workspace", f"driver profile #{d.get('id')}")
        except Exception as exc:
            say("FAIL", "Driver workspace", str(exc)[:100])

    if "dispatcher" in clients:
        try:
            s, _ = clients["dispatcher"].call("/api/optimizer/summary")
            say("OK", "Dispatch summary", f"{s.get('pending_orders', 0)} pending, {s.get('available_vehicles', 0)} vehicles")
        except Exception as exc:
            say("FAIL", "Operations flow", str(exc)[:100])

    if "fleet_manager" in clients:
        try:
            vehicles, _ = clients["fleet_manager"].call("/api/vehicles")
            say("OK" if vehicles else "WARN", "Fleet workspace", f"{len(vehicles)} vehicles")
        except Exception as exc:
            say("FAIL", "Fleet workspace", str(exc)[:100])

    if "admin" in clients:
        try:
            sessions, _ = clients["admin"].call("/api/admin/sessions")
            rows = sessions if isinstance(sessions, list) else sessions.get("sessions", [])
            say("OK", "Admin session visibility", f"{len(rows)} active sessions")
        except Exception as exc:
            say("FAIL", "Admin flow", str(exc)[:100])

    return summary()


def summary():
    fails, warns = RESULTS.count("FAIL"), RESULTS.count("WARN")
    print("\n" + ("READY FOR THE DEMO" if not fails and not warns else
                  "Ready, with warnings above" if not fails else "NOT READY — fix the [FAIL] lines first"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
