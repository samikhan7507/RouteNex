import hmac, math
from typing import Optional
from fastapi import APIRouter, Depends, Query
from db import rows, tx, audit
from deps import current, roles, driver_of
from schemas import RideIn, ParcelIn, StatusIn, CancelIn, RateIn, OtpIn, CompleteIn
from security import RateLimiter
from services import pricing, trips, mlserve, weather
from services.errors import ApiError

router = APIRouter(prefix="/api", tags=["trips"])
otp_limiter = RateLimiter(5, 300)     # wrong start/delivery OTPs per trip
OPS = ("dispatcher", "fleet_manager", "admin")
LIST_Q = """SELECT r.*,u.name driver_name,p.weight_kg,p.size,p.recipient_name FROM rides r
            LEFT JOIN drivers d ON d.id=r.driver_id LEFT JOIN users u ON u.id=d.user_id LEFT JOIN parcels p ON p.ride_id=r.id"""


def _distance(x):
    try:
        return pricing.resolve_distance(x.pickup_lat, x.pickup_lng, x.drop_lat, x.drop_lng, x.route_distance_km, x.route_duration_min)
    except ValueError as e:
        raise ApiError(400, str(e))


def _options(c, d, sg, tf, x, parcel=None):
    out = []
    classes = pricing.RIDE_CLASSES if parcel is None else {k: pricing.PARCEL_CLASSES[k] for k in pricing.feasible_parcel_classes(parcel.weight_kg)}
    for cls, cfg in classes.items():
        q = pricing.ride_quote(cls, d["distance_km"], sg, tf) if parcel is None else pricing.parcel_quote(cls, d["distance_km"], parcel.weight_kg, parcel.size, parcel.fragile, sg, tf)
        _with_ml_eta(q, cls, d["distance_km"], x, parcel)
        n, near = trips.availability(c, cls, x.pickup_lat, x.pickup_lng)
        out.append({**q, "nearby": n, "pickup_eta_min": max(2, math.ceil(near / cfg["speed"] * 60)) if near is not None else None})
    return out


def _with_ml_eta(q, cls, km, x, parcel=None):
    """Replace the formula ETA by the trained model's (when available) and attach plain-language reasons."""
    m = mlserve.predict_eta(cls, km, x.pickup_lat, x.pickup_lng, parcel.weight_kg if parcel else 0.0)
    q["factors"] = m["factors"] if m else []
    q["eta_source"] = "ml" if m else "formula"
    if m:
        q["eta_min"] = m["eta_min"]
    return q


def _estimate(x, uid, parcel=None):
    d = _distance(x)
    with tx() as c:
        sg, tf = trips.market(c)
        opts = _options(c, d, sg, tf, x, parcel)
        want = (parcel.vehicle_class if parcel else x.vehicle_class)
        sel = next((o for o in opts if o["vehicle_class"] == want), opts[0])
        disc, err = 0.0, None
        if x.coupon:
            try:
                disc, _ = trips.evaluate_coupon(c, uid, x.coupon, sel["fare"], "parcel" if parcel else "ride")
            except ApiError as e:
                err = e.detail
    return {"distance_km": d["distance_km"], "fare": sel["fare"], "eta_min": sel["eta_min"], "traffic_factor": tf, "surge": sg,
            "vehicle_class": sel["vehicle_class"], "options": opts, "discount": disc, "payable": round(sel["fare"] - disc, 2), "coupon_error": err,
            "eta_source": sel.get("eta_source"), "weather": {"rain": weather.snapshot()["rain"], "source": weather.snapshot()["source"]}}


@router.post("/rides/estimate")
def ride_estimate(x: RideIn, u=Depends(current)):
    return _estimate(x, u["id"])


@router.post("/parcels/estimate")
def parcel_estimate(x: ParcelIn, u=Depends(current)):
    return _estimate(x, u["id"], parcel=x)


def _book(u, x, kind, cls, parcel=None):
    d = _distance(x)
    with tx() as c:
        lim = 1 if kind == "ride" else 5
        if c.execute("SELECT COUNT(*) FROM rides WHERE user_id=? AND kind=? AND status IN ('searching','matched','arriving','started')", (u["id"], kind)).fetchone()[0] >= lim:
            raise ApiError(409, "You already have an active ride" if kind == "ride" else "You already have the maximum number of active parcels")
        sg, tf = trips.market(c)
        q = pricing.ride_quote(cls, d["distance_km"], sg, tf) if kind == "ride" else pricing.parcel_quote(cls, d["distance_km"], parcel.weight_kg, parcel.size, parcel.fragile, sg, tf)
        _with_ml_eta(q, cls, d["distance_km"], x, parcel)
        rid = trips.create_trip(c, u, kind, cls, (x.pickup, x.pickup_lat, x.pickup_lng), (x.dropoff, x.drop_lat, x.drop_lng),
                                {**q, "distance_km": d["distance_km"]}, x.payment_method, x.coupon,
                                parcel=None if not parcel else {"weight_kg": parcel.weight_kg, "size": parcel.size, "fragile": parcel.fragile, "description": parcel.description,
                                                                "recipient_name": parcel.recipient_name or u["name"], "recipient_phone": parcel.recipient_phone or ""})
        snap = trips.snapshot(c, trips.get(c, rid), u)
    audit(u["id"], "CREATE", kind, rid)
    return snap


@router.post("/rides")
def create_ride(x: RideIn, u=Depends(roles("customer", "admin"))):
    return _book(u, x, "ride", x.vehicle_class)


@router.post("/parcels")
def create_parcel(x: ParcelIn, u=Depends(roles("customer", "admin"))):
    feasible = pricing.feasible_parcel_classes(x.weight_kg)
    cls = x.vehicle_class or feasible[0]
    if cls not in feasible:
        raise ApiError(400, f"{pricing.PARCEL_CLASSES[cls]['label']} carries up to {pricing.PARCEL_CLASSES[cls]['max_kg']} kg")
    if not x.recipient_phone or len(x.recipient_phone) != 10 or not x.recipient_phone.isdigit():
        raise ApiError(400, "Enter the recipient's 10-digit phone number")
    return _book(u, x, "parcel", cls, parcel=x)


@router.get("/drivers/nearby")
def drivers_nearby(lat: float = Query(..., ge=-90, le=90), lng: float = Query(..., ge=-180, le=180), cls: str = Query("cab"), u=Depends(current)):
    if cls not in trips.CLASS_VEHICLES:
        raise ApiError(400, "Unknown vehicle class")
    with tx() as c:
        return trips.nearby(c, cls, lat, lng)


@router.get("/rides")
def rides(kind: Optional[str] = Query(None, pattern="^(ride|parcel)$"), u=Depends(current)):
    where, args = [], []
    if u["role"] == "customer":
        where.append("r.user_id=?"); args.append(u["id"])
    elif u["role"] == "driver":
        d = driver_of(u)
        if not d:
            return []
        where.append("r.driver_id=?"); args.append(d["id"])
    if kind:
        where.append("r.kind=?"); args.append(kind)
    sql = LIST_Q + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY r.id DESC LIMIT 300"
    with tx() as c:   # let demo trips progress even if the user never opens the tracking screen
        for r in c.execute("SELECT r.id FROM rides r WHERE r.status IN ('searching','matched','arriving','started') " + (" AND " + " AND ".join(where) if where else ""), args).fetchall():
            trips.advance(c, r["id"])
    return [trips.strip_private(r, u) for r in rows(sql, args)]


def _visible(c, r, u):
    if not r:
        raise ApiError(404, "Trip not found")
    if u["role"] == "customer" and r["user_id"] != u["id"]:
        raise ApiError(404, "Trip not found")
    if u["role"] == "driver":
        d = driver_of(u)
        if not d or r["driver_id"] != d["id"]:
            raise ApiError(403, "This trip is not assigned to you")


@router.get("/rides/{rid}/track")
def track(rid: int, u=Depends(current)):
    with tx() as c:
        _visible(c, trips.get(c, rid), u)
        return trips.snapshot(c, trips.advance(c, rid), u)


def _own(c, rid, u):
    r = trips.get(c, rid)
    d = driver_of(u)
    if not r:
        raise ApiError(404, "Trip not found")
    if not d or r["driver_id"] != d["id"]:
        raise ApiError(403, "This trip is not assigned to you")
    return r


@router.post("/rides/{rid}/arrived")
def arrived(rid: int, u=Depends(roles("driver"))):
    with tx() as c:
        r = _own(c, rid, u)
        if r["status"] != "matched":
            raise ApiError(409, f"Cannot mark arrived from {r['status']}")
        c.execute("UPDATE rides SET status='arriving',arrived_at=? WHERE id=? AND status='matched'", (trips.now_s(), rid))
        return trips.snapshot(c, trips.get(c, rid), u)


def _check_otp(rid, given, expected):
    key = f"trip:{rid}"
    if otp_limiter.is_blocked(key):
        raise ApiError(429, "Too many wrong OTPs for this trip. Ask the customer to check the code.")
    if not given or not expected or not hmac.compare_digest(given, expected):
        otp_limiter.record(key)
        raise ApiError(401, "Wrong OTP")
    otp_limiter.clear(key)


@router.post("/rides/{rid}/start")
def start(rid: int, x: OtpIn, u=Depends(roles("driver"))):
    with tx() as c:
        r = _own(c, rid, u)
        if r["status"] != "arriving":
            raise ApiError(409, "Mark arrived first, then start with the customer's OTP")
        _check_otp(rid, x.otp, r["otp"])
        c.execute("UPDATE rides SET status='started',started_at=? WHERE id=? AND status='arriving'", (trips.now_s(), rid))
        return trips.snapshot(c, trips.get(c, rid), u)


@router.post("/rides/{rid}/complete")
def complete(rid: int, x: Optional[CompleteIn] = None, u=Depends(roles("driver"))):
    with tx() as c:
        r = _own(c, rid, u)
        if r["status"] != "started":
            raise ApiError(409, f"Cannot complete from {r['status']}")
        if r["kind"] == "parcel":
            p = c.execute("SELECT delivery_otp FROM parcels WHERE ride_id=?", (rid,)).fetchone()
            _check_otp(rid, x.otp if x else None, p["delivery_otp"] if p else None)
        trips.complete_trip(c, r)
        return trips.snapshot(c, trips.get(c, rid), u)


@router.post("/rides/{rid}/cancel")
def cancel(rid: int, x: Optional[CancelIn] = None, u=Depends(current)):
    with tx() as c:
        r = trips.get(c, rid)
        _visible(c, r, u)
        if u["role"] not in ("customer", "admin", "dispatcher"):
            raise ApiError(403, "Insufficient permission")
        res = trips.cancel_trip(c, r, "customer" if u["role"] == "customer" else "ops", (x.reason if x else "Cancelled"))
        snap = trips.snapshot(c, trips.get(c, rid), u)
    audit(u["id"], "CANCEL", "trip", rid)
    return {**snap, **res}


@router.post("/rides/{rid}/rate")
def rate(rid: int, x: RateIn, u=Depends(roles("customer"))):
    with tx() as c:
        r = trips.get(c, rid)
        _visible(c, r, u)
        if r["status"] != "completed":
            raise ApiError(409, "You can rate a trip after it is completed")
        if c.execute("UPDATE rides SET rating=?,review=? WHERE id=? AND rating IS NULL", (x.rating, x.review, rid)).rowcount != 1:
            raise ApiError(409, "You have already rated this trip")
        c.execute("UPDATE drivers SET capacity_rating=ROUND((capacity_rating*rating_count+?)/(rating_count+1),2),rating_count=rating_count+1 WHERE id=?", (x.rating, r["driver_id"]))
    return {"id": rid, "rating": x.rating}


@router.patch("/rides/{rid}/status")
def ride_status(rid: int, x: StatusIn, u=Depends(current)):
    """Manual override kept for dispatchers/admins (and the old customer-cancel call). Drivers use /arrived /start /complete."""
    with tx() as c:
        r = trips.get(c, rid)
        _visible(c, r, u)
        if u["role"] == "customer":
            if x.status != "cancelled":
                raise ApiError(403, "Customers can only cancel their own trip")
        elif u["role"] == "driver":
            if x.status != "arriving":
                raise ApiError(403, "Use the OTP buttons to start and finish a trip")
        elif u["role"] not in ("dispatcher", "admin"):
            raise ApiError(403, "Insufficient permission")
        flow = {"searching": {"cancelled"}, "matched": {"arriving", "cancelled"}, "arriving": {"started", "cancelled"}, "started": {"completed"}}
        if x.status not in flow.get(r["status"], set()):
            raise ApiError(409, f"Cannot move trip from {r['status']} to {x.status}")
        now = trips.now_s()
        if x.status == "cancelled":
            trips.cancel_trip(c, r, "customer" if u["role"] == "customer" else "ops", "Cancelled")
        elif x.status == "arriving":
            c.execute("UPDATE rides SET status='arriving',arrived_at=? WHERE id=?", (now, rid))
        elif x.status == "started":
            c.execute("UPDATE rides SET status='started',started_at=? WHERE id=?", (now, rid))
        else:
            trips.complete_trip(c, r)
    audit(u["id"], "STATUS", "ride", rid, x.status)
    return {"id": rid, "status": x.status}
