from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.ratelimit import consume
from app.core.security import current_user, require_roles
from app.db import get_db
from app.models import Driver, Trip, User, Vehicle
from app.schemas import BookTripInput, CancelInput, RatingInput, TripQuoteInput
from app.services import pricing, routing, trips
from app.services.common import audit, locked
from app.services.geo import haversine_km
from app.services.serializers import trip

router = APIRouter(prefix="/api", tags=["rides and parcels"])


@router.post("/trips/quote")
def quote(body: TripQuoteInput, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    consume(db, f"quote:{user.id}", 30, 60, commit=True)
    road = routing.route((body.pickup.lat, body.pickup.lng), (body.drop.lat, body.drop.lng))
    waiting = db.scalar(select(func.count(Trip.id)).where(Trip.status == "searching"))
    free = db.scalar(select(func.count(Driver.id)).where(Driver.status == "available", Driver.online.is_(True)))
    data = pricing.quote_all(body, road, waiting, free)
    return {**data, "quote_token": pricing.issue_quote(user.id, {k: v for k, v in data.items() if k != "geometry"}), "expires_in": 300}


@router.post("/trips", status_code=201)
def book(body: BookTripInput, request: Request, user: User = Depends(require_roles("customer", "admin")), db: Session = Depends(get_db)):
    consume(db, f"book:{user.id}", 10, 60, commit=True)
    data = pricing.read_quote(body.quote_token, user.id)
    t = trips.create(db, user, body, data)
    db.flush()
    db.refresh(t)
    return trip(t, user)


@router.get("/trips")
def list_trips(kind: str = Query("", pattern="^(|ride|parcel|active|history)$"), page: int = Query(1, ge=1),
               user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Trip)
    if user.role == "customer":
        query = query.where(Trip.user_id == user.id)
    elif user.role == "driver":
        driver = db.scalar(select(Driver).where(Driver.user_id == user.id))
        query = query.where(Trip.driver_id == driver.id) if driver else query.where(False)
    if kind in ("ride", "parcel"):
        query = query.where(Trip.kind == kind)
    elif kind == "active":
        query = query.where(Trip.status.in_(trips.ACTIVE))
    elif kind == "history":
        query = query.where(Trip.status.in_(["completed", "cancelled", "expired"]))
    rows = db.scalars(query.order_by(Trip.id.desc()).offset((page - 1) * 50).limit(50)).all()
    return [trip(t, user) for t in rows]


@router.get("/trips/{trip_id}")
def detail(trip_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.get(Trip, trip_id)
    if not t or (user.role == "customer" and t.user_id != user.id):
        raise HTTPException(404, "Trip not found")
    if user.role == "driver" and (not t.driver or t.driver.user_id != user.id):
        raise HTTPException(403, "This trip is not assigned to you")
    return trip(t, user)


@router.post("/trips/{trip_id}/cancel")
def cancel_trip(trip_id: int, body: CancelInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = locked(db, Trip, trip_id, user.id if user.role == "customer" else None)
    trips.cancel(db, user, t, body.reason)
    return trip(t, user)


@router.post("/trips/{trip_id}/rate")
def rate(trip_id: int, body: RatingInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = locked(db, Trip, trip_id, user.id)
    if t.status != "completed" or not t.driver:
        raise HTTPException(409, "Only a completed trip can be rated")
    if t.rating is not None:
        raise HTTPException(409, "You have already rated this trip")
    t.rating, t.review = body.rating, body.review
    d = t.driver
    total = d.rating * d.rating_count + body.rating
    d.rating_count += 1
    d.rating = round(total / d.rating_count, 2)
    audit(db, user, "RATE", "trip", t.id, {"rating": body.rating})
    return trip(t, user)


@router.get("/drivers/nearby")
def nearby(lat: float = Query(ge=-90, le=90), lng: float = Query(ge=-180, le=180),
           vehicle_class: str = Query("cab"), user: User = Depends(current_user), db: Session = Depends(get_db)):
    if vehicle_class not in trips.CLASS_VEHICLES:
        raise HTTPException(422, "Unknown vehicle class")
    rows = db.scalars(select(Driver).join(Vehicle).where(Driver.online.is_(True), Driver.status == "available",
                    Vehicle.status == "available", Vehicle.type.in_(trips.CLASS_VEHICLES[vehicle_class]))).all()
    out = []
    for d in rows:
        if d.lat is None or d.lng is None:
            continue
        km = haversine_km(lat, lng, float(d.lat), float(d.lng))
        if km <= 10:
            out.append({"lat": round(float(d.lat), 4), "lng": round(float(d.lng), 4), "eta_min": max(2, round(km / 25 * 60)), "vehicle_type": d.vehicle.type})
    return sorted(out, key=lambda x: x["eta_min"])[:12]
