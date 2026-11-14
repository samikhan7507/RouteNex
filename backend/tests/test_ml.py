"""ML pipeline tests - pure Python/scikit-learn, no web server needed."""
import functools, json, pathlib, tempfile, time
from datetime import datetime
from ml import train, features as F
from services import mlserve, weather
from services.pricing import IST


@functools.lru_cache(maxsize=1)
def trained():
    d = pathlib.Path(tempfile.mkdtemp(prefix="rn_ml_"))
    report = train.run(d, n_eta=12000, n_delay=9000, days=70, log=lambda *a: None)
    return d, report


def activate():
    d, _ = trained(); mlserve.ART = d; mlserve._state.update(models={}, reg_mtime=0.0, forecast=None)


def deactivate():
    mlserve.ART = pathlib.Path(tempfile.mkdtemp(prefix="rn_ml_empty_")); mlserve._state.update(models={}, reg_mtime=0.0, forecast=None)


def at(hour, day=14):   # Oct 14 2026 is a Wednesday
    return datetime(2026, 10, day, hour, 0, tzinfo=IST)


def test_models_beat_their_baselines_and_pass_gates():
    _, rep = trained(); m = rep["models"]
    assert all(x["promoted"] for x in m.values())
    assert m["eta"]["metrics"]["mae_improvement_pct"] >= 5 and m["eta"]["metrics"]["r2"] >= 0.5
    assert m["delay"]["metrics"]["auc"] >= 0.70 > m["delay"]["metrics"]["baseline_auc_prior"]
    assert m["demand"]["metrics"]["mae_improvement_pct"] >= 0


def test_validation_is_temporal_not_random():
    import numpy as np
    day = np.repeat(np.arange(30), 10); tr, te = train._split(day, 7)
    assert day[tr].max() < day[te].min() and te.sum() == 70


def test_eta_responds_sensibly_to_distance_peak_and_rain():
    activate()
    a = mlserve.predict_eta("cab", 5, 26.91, 75.79, when=at(14))["eta_min"]
    b = mlserve.predict_eta("cab", 15, 26.91, 75.79, when=at(14))["eta_min"]
    peak = mlserve.predict_eta("cab", 8, 26.91, 75.79, when=at(18)); off = mlserve.predict_eta("cab", 8, 26.91, 75.79, when=at(14))
    assert b > a and peak["eta_min"] > off["eta_min"] and any("traffic" in f.lower() for f in peak["factors"])
    weather._cache.update(at=time.time(), data={"rain": True, "precip_mm": 2.0, "temp_c": 24, "hourly_rain": [1] * 24, "source": "open-meteo"})
    wet = mlserve.predict_eta("cab", 8, 26.91, 75.79, when=at(14)); assert wet["eta_min"] >= off["eta_min"]
    weather._cache.update(at=0.0, data=None)


def test_delay_risk_rises_when_slack_shrinks():
    activate()
    def stop(slack): return {"slack": slack, "seq": 4, "n_stops": 8, "leg_km": 6, "route_km": 30, "load_ratio": .8, "hour": 18, "priority": 3, "vtype": "Van", "lat": 26.91, "lng": 75.79}
    (tight, mid, loose), src = mlserve.delay_risks([stop(-5), stop(15), stop(60)])
    assert src == "ml" and tight["risk"] > mid["risk"] > loose["risk"] and tight["level"] in ("medium", "high") and loose["level"] == "low"
    assert "Tight window" in tight["factors"]


def test_demand_forecast_shape_and_evening_peak():
    activate(); f = mlserve.forecast(24)
    assert len(f["total"]) == 24 and f["source"] == "ml" and all(l <= t <= h for l, t, h in zip(f["low"], f["total"], f["high"]))
    by_hour = dict(zip(f["hours"], f["total"])); assert by_hour[19] > 2 * by_hour[4]
    hs = mlserve.hotspots(2, 3); assert len(hs) == 3 and hs[0]["expected"] >= hs[2]["expected"]
    assert 0.95 <= mlserve.demand_adjust() <= 1.10


def test_failed_gate_keeps_previous_model():
    d = pathlib.Path(tempfile.mkdtemp(prefix="rn_gate_"))
    first = train.run(d, n_eta=6000, n_delay=5000, days=70, log=lambda *a: None)
    before = json.loads((d / "registry.json").read_text())["eta"]["current"]
    old = train.GATES["eta"]["mae_improvement_pct_min"]; train.GATES["eta"]["mae_improvement_pct_min"] = 99.0
    try:
        time.sleep(1.1)                                              # new version stamp
        second = train.run(d, n_eta=6000, n_delay=5000, days=70, log=lambda *a: None)
    finally:
        train.GATES["eta"]["mae_improvement_pct_min"] = old
    assert second["models"]["eta"]["promoted"] is False and json.loads((d / "registry.json").read_text())["eta"]["current"] == before


def test_graceful_fallback_without_models():
    deactivate()
    assert mlserve.predict_eta("cab", 8, 26.9, 75.8) is None
    (r,), src = mlserve.delay_risks([{"slack": 2, "seq": 1, "n_stops": 3, "leg_km": 2, "route_km": 5, "load_ratio": .3, "hour": 12, "priority": 1, "vtype": "Bike", "lat": 26.9, "lng": 75.8}])
    assert src == "heuristic" and 0 <= r["risk"] <= 1
    f = mlserve.forecast(24); assert f["source"] == "heuristic" and len(f["total"]) == 24 and mlserve.demand_adjust() == 1.0
