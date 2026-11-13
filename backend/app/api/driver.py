from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import require_roles
from app.db import get_db
from app.models import Driver, DriverEarning, Trip, User
from app.schemas import DriverUpdate, ProofInput
from app.services import trips
from app.services.common import audit, locked
from app.services.serializers import driver, trip

router = APIRouter(prefix="/api/driver", tags=["driver"])


def own_driver(user: User, db: Session) -> Driver:
    d = db.scalar(select(Driver).where(Driver.user_id == user.id))
    if not d:
        raise HTTPException(404, "No driver profile is linked to this account")
    return d


@router.get("/me")
def me(user: User = Depends(require_roles("driver")), db: Session = Depends(get_db)):
    return driver(own_driver(user, db), private=True)


@router.patch("/me")
def update(body: DriverUpdate, user: User = Depends(require_roles("driver")), db: Session = Depends(get_db)):
    d = db.scalar(select(Driver).where(Driver.user_id == user.id).with_for_update())
    if not d:
        raise HTTPException(404, "Driver profile not found")
    if body.online is not None:
        if body.online and d.status not in ("available", "offline"):
            raise HTTPException(409, "Finish your current work before changing availability")
        d.online = body.online
        if d.status in ("available", "offline"):
            d.status = "available" if body.online else "offline"
    if body.lat is not None and body.lng is not None:
        d.lat, d.lng = body.lat, body.lng
        if d.vehicle:
            d.vehicle.lat, d.vehicle.lng = body.lat, body.lng
    if body.vehicle_id is not None and body.vehicle_id != d.vehicle_id:
        if d.status != "available":
            raise HTTPException(409, "Vehicle changes require fleet manager approval while assigned")
        d.vehicle_id = body.vehicle_id
    audit(db, user, "DRIVER_UPDATE", "driver", d.id)
    return driver(d, private=True)


@router.get("/requests")
def requests(user: User = Depends(require_roles("driver")), db: Session = Depends(get_db)):
    d = own_driver(user, db)
    if not d.online or d.status != "available":
        return []
    rows = db.scalars(select(Trip).where(Trip.status == "searching").order_by(Trip.id)).all()
    # Evaluate each trip's vehicle/weight constraints, not just the first one.
    return [trip(t, user) for t in rows if d.id in {x.id for x in trips.eligible_drivers(db, t)}]


@router.post("/requests/{trip_id}/accept")
def accept(trip_id: int, user: User = Depends(require_roles("driver")), db: Session = Depends(get_db)):
    d = db.scalar(select(Driver).where(Driver.user_id == user.id).with_for_update())
    t = locked(db, Trip, trip_id)
    if not trips.match(db, t, chosen=d):
        raise HTTPException(409, "This request is no longer available or your vehicle is not eligible")
    return trip(t, user)


@router.get("/trips")
def my_trips(user: User = Depends(require_roles("driver")), db: Session = Depends(get_db)):
    d = own_driver(user, db)
    rows = db.scalars(select(Trip).where(Trip.driver_id == d.id).order_by(Trip.id.desc()).limit(100))
    return [trip(t, user) for t in rows]


@router.post("/trips/{trip_id}/{action}")
def action(trip_id: int, action: str, body: ProofInput | None = None, user: User = Depends(require_roles("driver")), db: Session = Depends(get_db)):
    if action not in ("arrive", "start", "complete"):
        raise HTTPException(404, "Unknown driver action")
    t = locked(db, Trip, trip_id)
    trips.advance(db, user, t, action, body.code if body else None)
    return trip(t, user)


@router.get("/earnings")
def earnings(user: User = Depends(require_roles("driver")), db: Session = Depends(get_db)):
    d = own_driver(user, db)
    rows = db.scalars(select(DriverEarning).where(DriverEarning.driver_id == d.id).order_by(DriverEarning.id.desc()).limit(100)).all()
    payable = db.scalar(select(func.coalesce(func.sum(DriverEarning.net_paise), 0)).where(DriverEarning.driver_id == d.id, DriverEarning.status == "payable"))
    paid = db.scalar(select(func.coalesce(func.sum(DriverEarning.net_paise), 0)).where(DriverEarning.driver_id == d.id, DriverEarning.status == "paid"))
    return {"payable": payable / 100, "paid": paid / 100, "commission_rate": 0.20,
            "note": "Net payable after the disclosed 20% platform fee. Settlement is recorded by operations, not an automatic bank transfer.",
            "entries": [{"id": e.id, "trip_id": e.trip_id, "gross": e.gross_paise / 100, "platform_fee": e.platform_fee_paise / 100,
                         "net": e.net_paise / 100, "status": e.status, "settlement_reference": e.settlement_reference,
                         "created_at": e.created_at, "paid_at": e.paid_at} for e in rows]}
