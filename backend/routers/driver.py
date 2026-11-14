from datetime import datetime
from fastapi import APIRouter, Depends
from db import rows, one, tx, run
from deps import roles, driver_of
from schemas import OnlineIn
from services import trips
from services.errors import ApiError
from services.pricing import IST

router = APIRouter(prefix="/api/driver", tags=["driver"])
TS = "COALESCE(completed_at, CAST(strftime('%s',created_at) AS INTEGER))"


def _me(u):
    d = driver_of(u)
    if not d:
        raise ApiError(404, "No driver profile is linked to this account")
    return d


@router.get("/job")
def current_job(u=Depends(roles("driver"))):
    d = _me(u)
    with tx() as c:
        r = c.execute("SELECT id FROM rides WHERE driver_id=? AND status IN ('matched','arriving','started') ORDER BY id DESC LIMIT 1", (d["id"],)).fetchone()
        job = trips.snapshot(c, trips.advance(c, r["id"]), u) if r else None
        if job and job["status"] == "completed":
            job = None
    return {"online": bool(d["online"]), "job": job}


@router.post("/online")
def set_online(x: OnlineIn, u=Depends(roles("driver"))):
    d = _me(u)
    if not x.online and one("SELECT 1 FROM rides WHERE driver_id=? AND status IN ('matched','arriving','started')", (d["id"],)):
        raise ApiError(409, "Finish your current trip before going offline")
    run("UPDATE drivers SET online=? WHERE id=?", (1 if x.online else 0, d["id"]))
    return {"online": x.online}


def _sum(d_id, since):
    r = one(f"SELECT COUNT(*) n, COALESCE(SUM(fare),0) g FROM rides WHERE driver_id=? AND status='completed' AND {TS}>=?", (d_id, since))
    return {"trips": r["n"], "earnings": round(r["g"] * trips.DRIVER_SHARE, 2)}


@router.get("/earnings")
def earnings(u=Depends(roles("driver"))):
    d = _me(u)
    day0 = int(datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    recent = rows(f"SELECT id,kind,pickup,dropoff,fare,{TS} at FROM rides WHERE driver_id=? AND status='completed' ORDER BY id DESC LIMIT 8", (d["id"],))
    for r in recent:
        r["earning"] = round(r["fare"] * trips.DRIVER_SHARE, 2)
    return {"online": bool(d["online"]), "rating": d["capacity_rating"], "rating_count": d["rating_count"],
            "today": _sum(d["id"], day0), "week": _sum(d["id"], day0 - 6 * 86400), "total": _sum(d["id"], 0), "recent": recent}


@router.get("/route")
def my_route(u=Depends(roles("driver"))):
    """The driver's active delivery route (shop orders planned by the optimizer): ordered stops, ETAs, what to collect."""
    d = _me(u)
    r = one("""SELECT r.id,r.status,r.distance_km,r.duration_min,r.load_kg,r.reason,v.plate,v.type vtype,v.capacity_kg,v.lat vlat,v.lng vlng FROM routes r
               LEFT JOIN vehicles v ON v.id=r.vehicle_id WHERE r.driver_id=? AND r.status IN ('planned','active') ORDER BY r.id DESC LIMIT 1""", (d["id"],))
    if not r:
        return {"route": None}
    r["stops"] = rows("""SELECT ro.stop_sequence seq,ro.eta,ro.arrival_min,o.id order_id,o.status,o.delivery_window,o.weight_kg,o.lat,o.lng,o.priority,
                         o.payment_method,o.payment_status,o.total,u.name customer,u.phone,a.line1 address FROM route_orders ro JOIN orders o ON o.id=ro.order_id
                         JOIN users u ON u.id=o.user_id LEFT JOIN addresses a ON a.id=o.address_id WHERE ro.route_id=? ORDER BY ro.stop_sequence""", (r["id"],))
    for s in r["stops"]:
        s["collect"] = round(s["total"], 2) if s["payment_method"] == "cod" and s["payment_status"] != "paid" else 0
    return {"route": r}
