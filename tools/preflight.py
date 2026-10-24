"""RouteNex pre-demo check. Start the app first (start.bat), then run preflight.bat. Uses only the standard library.
Prints OK / WARN / FAIL for everything that can embarrass you on stage, with the fix next to each problem."""
import json, os, shutil, sys, time, urllib.request, urllib.error

BASE = os.getenv("ROUTENEX_URL", "http://localhost:8000")
RESULTS = []


def say(level, name, detail="", fix=""):
    RESULTS.append(level)
    icon = {"OK": "[ OK ]", "WARN": "[WARN]", "FAIL": "[FAIL]"}[level]
    print(f"{icon} {name}" + (f" - {detail}" if detail else ""))
    if fix and level != "OK":
        print(f"        fix: {fix}")


def call(path, method="GET", body=None, token=None, timeout=6):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def login(email, pw="Demo@123"):
    try:
        return call("/api/auth/login", "POST", {"email": email, "password": pw})["access_token"]
    except Exception:
        return None


def online(url, timeout=3):
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "routenex-preflight"}), timeout=timeout).read(64)
        return True
    except Exception:
        return False


def main():
    print(f"RouteNex pre-demo check against {BASE}\n")
    try:
        h = call("/api/health")
        say("OK" if h.get("status") == "healthy" else "FAIL", "Server and database", h.get("status", "?"))
    except Exception as e:
        say("FAIL", "Server is not reachable", str(e)[:80], "double-click start.bat and wait for 'Application startup complete'")
        return summary()
    cust, disp, drv = login("customer@routenex.in"), login("dispatcher@routenex.in"), login("driver@routenex.in")
    for who, tok in (("customer", cust), ("dispatcher", disp), ("driver", drv)):
        say("OK" if tok else "WARN", f"Demo login: {who}", "works" if tok else "failed", "run reset_demo.bat to restore the demo accounts")
    if cust:
        try:
            w = call("/api/wallet", token=cust)["balance"]
            say("OK" if w >= 300 else "WARN", "Customer wallet", f"Rs {w:.0f}", "top up from the Wallet page, or run reset_demo.bat")
            a = call("/api/assistant/status", token=cust)
            say("OK", "Assistant engine", a["provider"] + (" (private, local)" if a["provider"].startswith("ollama") else " (built-in, no AI model)" if a["provider"] == "offline" else " (cloud)"))
            est = call("/api/rides/estimate", "POST", {"pickup": "C-Scheme", "pickup_lat": 26.9124, "pickup_lng": 75.7873, "dropoff": "Airport", "drop_lat": 26.8242, "drop_lng": 75.8122}, token=cust)
            near = max(o["nearby"] for o in est["options"])
            say("OK" if near else "WARN", "Ride estimate and nearby drivers", f"{len(est['options'])} options, ETA source: {est.get('eta_source')}", "restart the app; demo drivers are created at startup")
            if est.get("eta_source") != "ml":
                say("WARN", "ML ETA", "using the formula fallback", "wait ~10 s after startup, or install scikit-learn (start.bat does) and restart")
        except Exception as e:
            say("FAIL", "Customer flow", str(e)[:90])
    if disp:
        try:
            st = call("/api/ml/status", token=disp)
            ready = all(st["models"].values())
            say("OK" if ready else "WARN", "ML models", "all 3 trained" + (" (training...)" if st["training"] else "") if ready else f"not ready: {st['models']}", "wait 10 s and rerun; or admin: Analytics & ML -> Retrain models")
            ov = call("/api/optimizer/overview", token=disp)
            say("OK" if ov["pending"] >= 3 and ov["vehicles"] >= 3 else "WARN", "Optimizer has work to do", f"{ov['pending']} orders waiting, {ov['vehicles']} vehicles ready", "run reset_demo.bat for fresh demo data (or place 3+ orders as a customer)")
        except Exception as e:
            say("FAIL", "Operations flow", str(e)[:90])
    net = {"OpenStreetMap tiles": "https://a.tile.openstreetmap.org/0/0/0.png", "Road routing (OSRM)": "https://router.project-osrm.org/route/v1/driving/75.78,26.91;75.81,26.82?overview=false",
           "Live weather (Open-Meteo)": "https://api.open-meteo.com/v1/forecast?latitude=26.91&longitude=75.79&current=temperature_2m"}
    for name, url in net.items():
        ok_ = online(url); say("OK" if ok_ else "WARN", name, "reachable" if ok_ else "NOT reachable", "maps and routes need internet; check Wi-Fi or switch the laptop to your phone hotspot")
    say("OK" if shutil.which("cloudflared") else "WARN", "cloudflared (phone link)", "installed" if shutil.which("cloudflared") else "not found", "winget install --id Cloudflare.cloudflared, then reopen the window")
    try:
        tags = json.load(urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=1))
        say("OK", "Ollama (optional local AI)", ", ".join(m["name"] for m in tags.get("models", [])) or "running, no model pulled")
    except Exception:
        say("OK", "Ollama (optional local AI)", "not running - assistant uses the built-in engine, which is fine")
    summary()


def summary():
    f, w = RESULTS.count("FAIL"), RESULTS.count("WARN")
    print("\n" + ("READY FOR THE DEMO" if not f and not w else "Ready, with warnings above" if not f else "NOT READY - fix the [FAIL] lines first"))
    sys.exit(1 if f else 0)


if __name__ == "__main__":
    main()
