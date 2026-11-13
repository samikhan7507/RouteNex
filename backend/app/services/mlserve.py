"""Model serving reads ONLY promoted registry entries; rejected candidates never become live."""
from __future__ import annotations
import json
import math
import threading
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np

from app.core.config import get_settings
from app.services import weather
from app.services.pricing import IST
from ml import features as F

_lock = threading.Lock()
_state = {"mtime": None, "models": {}, "registry": {}}


def _art() -> Path:
    return Path(get_settings().ml_artifact_dir)


def _load():
    path = _art() / "registry.json"
    if not path.exists():
        return
    mtime = path.stat().st_mtime_ns
    if mtime == _state["mtime"]:
        return
    with _lock:
        try:
            registry = json.loads(path.read_text())
            models = {}
            for name in ("eta", "delay", "demand"):
                entry = registry.get(name, {})
                file = _art() / entry.get("current", "")
                if entry.get("current") and file.exists():
                    models[name] = joblib.load(file)
            _state.update(mtime=mtime, models=models, registry=registry)
        except Exception:
            # Keep the last known-good models rather than serving a corrupt candidate.
            return


def status() -> dict:
    _load()
    return {"available": {n: n in _state["models"] for n in ("eta", "delay", "demand")},
            "registry": _state["registry"], "data_source": "synthetic unless an operator imports real training data",
            "note": "Only promoted models are served. Metrics below belong to the active artifact, not the latest rejected candidate."}


def predict_eta(vclass: str, km: float, lat: float, lng: float, load_kg: float = 0.0) -> dict | None:
    _load()
    m = _state["models"].get("eta")
    if not m:
        return None
    now = datetime.now(IST)
    zone = F.zone_index(lat, lng)
    rain = weather.snapshot()["rain"]
    row = F.eta_row(vclass, km, now.hour, now.weekday(), rain, zone, load_kg)
    value = max(3, int(round(float(np.expm1(m["model"].predict(np.array([row]))[0])))))
    return {"eta_min": value, "source": "ml-synthetic", "version": m.get("version")}


def forecast(hours: int = 24) -> dict:
    _load()
    now = datetime.now(IST)
    m = _state["models"].get("demand")
    rain = weather.snapshot()["hourly_rain"]
    labels, hs, dows = [], [], []
    for k in range(hours):
        t = now + timedelta(hours=k + 1)
        labels.append(t.strftime("%a %H:00"))
        hs.append(t.hour)
        dows.append(t.weekday())
    nz = len(F.ZONES)
    if m:
        X = np.array([[z, hs[k], dows[k], rain[k] if k < len(rain) else 0] for k in range(hours) for z in range(nz)])
        lam = np.maximum(m["model"].predict(X), 0).reshape(hours, nz)
        source = "ml-synthetic"
    else:
        lam = np.array([[14 * F.ZONES[z][3] * F.demand_curve(hs[k]) * F.demand_dow_mult(dows[k]) for z in range(nz)] for k in range(hours)])
        source = "heuristic"
    total = lam.sum(axis=1)
    return {"labels": labels, "total": [round(float(x), 1) for x in total],
            "low": [round(max(0, float(x) - 1.28 * math.sqrt(max(x, 0.5))), 1) for x in total],
            "high": [round(float(x) + 1.28 * math.sqrt(max(x, 0.5)), 1) for x in total],
            "zones": [z[0] for z in F.ZONES], "by_zone": [[round(float(x), 1) for x in row] for row in lam],
            "source": source, "weather_source": weather.snapshot()["source"]}
