"""Serving layer for the ML models. Loads the promoted artifacts from ml/artifacts, answers predictions, and ALWAYS degrades gracefully:
if scikit-learn or the artifacts are missing, every function returns None / a heuristic and the app keeps working."""
import json, os, sys, threading, time, pathlib, math
from datetime import datetime
import config
from services import weather
from services.pricing import IST

if str(config.ROOT) not in sys.path:
    sys.path.insert(0, str(config.ROOT))
try:
    import numpy as np
    import joblib
    from ml import features as F
    HAVE_ML = True
except Exception:          # numpy / scikit-learn not installed
    HAVE_ML = False
    from ml import features as F    # features.py is pure Python

ART = pathlib.Path(os.getenv("ROUTENEX_ML_DIR", str(config.ROOT / "ml" / "artifacts")))
_lock = threading.Lock()
_state = {"models": {}, "reg_mtime": 0.0, "training": False, "error": None, "last_run": None, "forecast": None}


def _registry():
    p = ART / "registry.json"
    return (json.loads(p.read_text()), p.stat().st_mtime) if p.exists() else (None, 0.0)


def _load():
    """(Re)load promoted models when registry.json changed. Cheap when nothing changed."""
    if not HAVE_ML:
        return
    reg, mt = _registry()
    if not reg or mt == _state["reg_mtime"]:
        return
    with _lock:
        models = {}
        for name in ("eta", "delay", "demand"):
            ent = reg.get(name)
            if ent and (ART / ent["current"]).exists():
                try:
                    models[name] = joblib.load(ART / ent["current"])
                except Exception as e:
                    _state["error"] = f"could not load {name}: {e}"
        _state.update(models=models, reg_mtime=mt, forecast=None)


def model(name):
    _load()
    return _state["models"].get(name)


def available():
    _load()
    return {n: (n in _state["models"]) for n in ("eta", "delay", "demand")}


def _now(when=None):
    return when or datetime.now(IST)


# ---------------- ETA ----------------
def predict_eta(vclass, km, lat, lng, load_kg=0.0, when=None):
    """-> {'eta_min', 'factors', 'source'} or None (caller then uses the formula)."""
    m = model("eta")
    if not m:
        return None
    t = _now(when); zone = F.zone_index(lat, lng); rain = weather.snapshot()["rain"]
    row = F.eta_row(vclass, km, t.hour, t.weekday(), rain, zone, load_kg)
    ref_traffic = F.eta_row(vclass, km, 14, 2, rain, zone, load_kg)
    ref_rain = F.eta_row(vclass, km, t.hour, t.weekday(), False, zone, load_kg)
    ref_load = F.eta_row(vclass, km, t.hour, t.weekday(), rain, zone, 0.0)
    p = np.expm1(m["model"].predict(np.array([row, ref_traffic, ref_rain, ref_load], dtype=float)))
    eta = max(3, int(round(float(p[0]))))
    factors = []
    for label, d in (("Heavy traffic", p[0] - p[1]), ("Rain", p[0] - p[2]), ("Heavy load", p[0] - p[3])):
        if d >= 1.0:
            factors.append((d, f"{label} +{int(round(d))} min"))
    factors.sort(reverse=True)
    return {"eta_min": eta, "factors": [f for _, f in factors[:2]], "source": "ml"}


# ---------------- delay risk ----------------
def delay_risks(stops):
    """stops: list of dicts {slack, seq, n_stops, leg_km, route_km, load_ratio, hour, priority, vtype, lat, lng}.
    -> (list of {'risk','level','factors'}, source)"""
    t = _now(); rain = weather.snapshot()["rain"]; m = model("delay"); out = []
    rows = []
    for s in stops:
        zone = F.zone_index(s["lat"], s["lng"]); h = int(s["hour"]) % 24; vc = F.vclass_code(F.VEHICLE_TYPE_TO_CLASS.get(s["vtype"], "truck"))
        rows.append([s["slack"], s["seq"], s["n_stops"], s["leg_km"], s["route_km"], s["load_ratio"], h, t.weekday(), int(rain), F.congestion(h, t.weekday(), zone, rain), s["priority"], vc])
    if not rows:
        return [], "none"
    if m:
        X = np.array(rows, dtype=float); p = m["model"].predict_proba(X)[:, 1]
        variants = {"Tight window": (0, 30.0), "Long leg": (3, 2.0), "Late in route": (1, 1.0), "Rain": (8, 0.0), "Peak traffic": (9, 0.1)}
        base = {name: m["model"].predict_proba(_with(X, idx, val))[:, 1] for name, (idx, val) in variants.items()}
        for i, risk in enumerate(p):
            fs = sorted(((risk - base[n][i], n) for n in variants), reverse=True)
            out.append({"risk": round(float(risk), 3), "level": _level(risk), "factors": [n for d, n in fs[:2] if d >= 0.05] if risk >= 0.25 else []})
        return out, "ml"
    for r in rows:                                               # heuristic: tighter window => riskier
        risk = 1 / (1 + math.exp((r[0] - 5) / 8)); out.append({"risk": round(risk, 3), "level": _level(risk), "factors": ["Tight window"] if risk >= 0.25 else []})
    return out, "heuristic"


def _with(X, idx, val):
    Y = X.copy(); Y[:, idx] = val; return Y


def _level(r):
    return "high" if r >= 0.5 else "medium" if r >= 0.25 else "low"


# ---------------- demand ----------------
def forecast(hours=24):
    """Expected requests per area per hour for the next `hours` (cached 10 min). -> dict or heuristic fallback."""
    cached = _state["forecast"]
    if cached and time.time() - cached["at"] < 600 and cached["hours"] == hours:
        return cached["data"]
    t = _now(); rain = weather.snapshot()["hourly_rain"]; m = model("demand")
    labels, dows, hs = [], [], []
    for k in range(hours):
        tt = t.replace(minute=0, second=0, microsecond=0).timestamp() + 3600 * (k + 1)
        d = datetime.fromtimestamp(tt, IST); labels.append(d.strftime("%a %H:00")); hs.append(d.hour); dows.append(d.weekday())
    nz = len(F.ZONES); per_zone = []
    if m:
        X = np.array([[z, hs[k], dows[k], rain[k] if k < len(rain) else 0] for k in range(hours) for z in range(nz)], dtype=float)
        lam = np.maximum(m["model"].predict(X), 0.0).reshape(hours, nz); disp = m["meta"].get("dispersion", 1.0); mean = m["meta"].get("mean_demand", float(lam.mean()) or 1.0); src = "ml"
    else:
        lam = np.array([[14 * F.ZONES[z][3] * F.demand_curve(hs[k]) * F.demand_dow_mult(dows[k]) for z in range(nz)] for k in range(hours)]) if HAVE_ML else None
        disp, mean, src = 1.0, 6.44, "heuristic"
    if lam is None:
        lam = [[14 * F.ZONES[z][3] * F.demand_curve(hs[k]) * F.demand_dow_mult(dows[k]) for z in range(nz)] for k in range(hours)]
        tot = [sum(r) for r in lam]
    else:
        tot = lam.sum(axis=1).tolist(); lam = lam.tolist()
    avg_total = (mean * nz) or 1.0
    band = [1.28 * disp * math.sqrt(max(v, 0.5)) * 1.0 for v in tot]
    data = {"labels": labels, "hours": hs, "total": [round(v, 1) for v in tot], "low": [round(max(0, v - b), 1) for v, b in zip(tot, band)], "high": [round(v + b, 1) for v, b in zip(tot, band)],
            "index": [round(v / avg_total, 2) for v in tot], "zones": [z[0] for z in F.ZONES], "by_zone": [[round(x, 1) for x in r] for r in lam], "source": src}
    _state["forecast"] = {"at": time.time(), "hours": hours, "data": data}
    return data


def hotspots(next_hours=2, top=3):
    f = forecast(max(next_hours, 2)); n = min(next_hours, len(f["labels"]))
    score = [sum(f["by_zone"][k][z] for k in range(n)) for z in range(len(f["zones"]))]
    order = sorted(range(len(score)), key=lambda z: -score[z])[:top]; avg = (sum(score) / len(score)) or 1.0
    return [{"zone": f["zones"][z], "expected": round(score[z], 1), "vs_avg": round(score[z] / avg, 2)} for z in order]


def demand_adjust():
    """Small price multiplier from the demand forecast for the coming hour (0.95 .. 1.10); 1.0 when no model."""
    if not model("demand"):
        return 1.0
    idx = forecast(24)["index"][0]
    return round(min(1.10, max(0.95, 1 + 0.2 * (idx - 1))), 3)


# ---------------- training / status ----------------
def _train_job():
    try:
        from ml import train
        _state["last_run"] = train.run(ART, log=lambda *a: None); _state["error"] = None
    except Exception as e:
        _state["error"] = f"training failed: {e}"
    finally:
        _state["training"] = False


def start_training():
    """Train in a background thread. -> True if started, False if already running / scikit-learn missing."""
    if not HAVE_ML or _state["training"]:
        return False
    _state["training"] = True
    threading.Thread(target=_train_job, daemon=True).start()
    return True


def ensure_models():
    """At startup: if nothing was ever trained, train once in the background (about 10 seconds)."""
    if HAVE_ML and os.getenv("ROUTENEX_ML_AUTOTRAIN", "1") != "0" and not (ART / "registry.json").exists():
        start_training()


def status():
    reg, _ = _registry(); _load()
    return {"sklearn": HAVE_ML, "models": available(), "training": _state["training"], "error": _state["error"], "trained_at": (reg or {}).get("trained_at"),
            "version": (reg or {}).get("version"), "data": "synthetic"}


def metrics():
    p = ART / "metrics.json"
    return json.loads(p.read_text()) if p.exists() else None
