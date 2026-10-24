from fastapi import APIRouter, Depends
from db import rows, one
from deps import roles
from services import mlserve, weather
from services.errors import ApiError

router = APIRouter(prefix="/api/ml", tags=["ml"])
OPS = ("dispatcher", "fleet_manager", "admin")


@router.get("/status")
def status(u=Depends(roles("driver", *OPS))):
    return {**mlserve.status(), "weather": weather.snapshot()}


@router.get("/hotspots")
def hotspots(u=Depends(roles("driver", *OPS))):
    """Areas expected to be busiest over the next two hours (from the demand model)."""
    return {"zones": mlserve.hotspots(2, 3), "source": mlserve.forecast(24)["source"]}


@router.post("/retrain")
def retrain(u=Depends(roles("admin"))):
    if not mlserve.HAVE_ML:
        raise ApiError(503, "scikit-learn is not installed on this server")
    if not mlserve.start_training():
        raise ApiError(409, "Training is already running")
    return {"started": True}


@router.get("/models")
def models(u=Depends(roles(*OPS))):
    return {"status": mlserve.status(), "report": mlserve.metrics()}


@router.get("/predictions")
def predictions(u=Depends(roles(*OPS))):
    st, met, fc, w = mlserve.status(), mlserve.metrics(), mlserve.forecast(24), weather.snapshot()
    risky = rows("""SELECT ro.order_id,ro.stop_sequence seq,ro.eta,ro.delay_risk risk,o.delivery_window,v.plate FROM route_orders ro JOIN routes r ON r.id=ro.route_id
                    JOIN orders o ON o.id=ro.order_id LEFT JOIN vehicles v ON v.id=r.vehicle_id WHERE r.status IN ('planned','active')
                    AND o.status NOT IN ('delivered','failed','cancelled') AND ro.delay_risk IS NOT NULL ORDER BY ro.delay_risk DESC LIMIT 8""")
    avg = one("""SELECT AVG(ro.delay_risk) a,COUNT(*) n FROM route_orders ro JOIN routes r ON r.id=ro.route_id JOIN orders o ON o.id=ro.order_id
                 WHERE r.status IN ('planned','active') AND o.status NOT IN ('delivered','failed','cancelled') AND ro.delay_risk IS NOT NULL""")
    veh = one("SELECT COUNT(*) n,SUM(CASE WHEN available=1 THEN 1 ELSE 0 END) a FROM vehicles")
    util = one("SELECT AVG(load_kg*1.0/NULLIF(v.capacity_kg,0)) u FROM routes r JOIN vehicles v ON v.id=r.vehicle_id WHERE r.load_kg IS NOT NULL")
    done = one("SELECT SUM(CASE WHEN status='delivered' THEN 1 ELSE 0 END) d,SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) f FROM orders")
    delivered, failed = (done["d"] or 0), (done["f"] or 0)
    success = delivered / (delivered + failed) if (delivered + failed) else None
    perf = round(100 * (0.6 * (success if success is not None else 0.9) + 0.4 * min(1.0, (util["u"] or 0.5)))) if success is not None or util["u"] else None
    observed = one("""SELECT (SELECT COUNT(*) FROM rides WHERE CAST(strftime('%s',created_at) AS INTEGER)>strftime('%s','now')-86400)
                      +(SELECT COUNT(*) FROM orders WHERE CAST(strftime('%s',created_at) AS INTEGER)>strftime('%s','now')-86400) n""")["n"]
    ml = (met or {}).get("models", {})
    eta_m, del_m, dem_m = (ml.get(k, {}).get("metrics", {}) for k in ("eta", "delay", "demand"))
    score = avg["a"]
    return {
        "status": st, "weather": w, "report": met, "forecast": fc, "hotspots": mlserve.hotspots(2, 5), "high_risk_stops": risky,
        "active_stops": avg["n"], "network_delay_risk": round(score, 3) if score is not None else None,
        "fleet_utilization_pct": round(100 * (1 - (veh["a"] or 0) / veh["n"]), 1) if veh["n"] else 0, "route_performance_score": perf, "requests_last_24h": observed,
        # backward-compatible fields for the older Analytics page
        "eta_model": {"mae_minutes": eta_m.get("mae_min"), "predicted_next_route_minutes": None, "confidence": eta_m.get("r2")},
        "delay_risk": {"score": score or 0.0, "level": "high" if (score or 0) >= 0.5 else "medium" if (score or 0) >= 0.25 else "low", "factors": []},
        "demand_forecast": {"tomorrow": round(sum(fc["total"])), "confidence": dem_m.get("r2"), "daily": [], "hourly": [{"hour": l, "demand": v} for l, v in zip(fc["labels"], fc["total"])]},
        "fleet_utilization_prediction": round((veh["n"] - (veh["a"] or 0)) / veh["n"], 2) if veh["n"] else 0, "routes": [],
        "model_note": "Models are trained on synthetic data; weather and fleet numbers are real.",
    }
