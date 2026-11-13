from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, require_roles
from app.db import get_db
from app.models import Alert, Driver, Maintenance, Route, User, Vehicle
from app.schemas import DriverInput, MaintenanceInput, VehicleInput, VehicleUpdate
from app.services.common import audit, paise
from app.services.dispatch import release_route
from app.services.serializers import driver, route, vehicle

router = APIRouter(prefix="/api", tags=["fleet"])
OPS = ("dispatcher", "fleet_manager", "admin")


@router.get("/vehicles")
def vehicles(user: User = Depends(require_roles(*OPS, "driver")), db: Session = Depends(get_db)):
    query = select(Vehicle).order_by(Vehicle.id)
    if user.role == "driver":
        d = db.scalar(select(Driver).where(Driver.user_id == user.id))
        query = query.where(Vehicle.id == d.vehicle_id) if d else query.where(False)
    return [vehicle(v) for v in db.scalars(query)]


@router.post("/vehicles", status_code=201)
def add_vehicle(body: VehicleInput, user: User = Depends(require_roles("fleet_manager", "admin")), db: Session = Depends(get_db)):
    data = body.model_dump()
    data["plate"] = data["plate"].upper()
    data["cost_per_km_paise"] = paise(data.pop("cost_per_km"))
    if db.scalar(select(Vehicle.id).where(Vehicle.plate == data["plate"])):
        raise HTTPException(409, "A vehicle with this plate already exists")
    v = Vehicle(**data)
    db.add(v)
    db.flush()
    audit(db, user, "CREATE", "vehicle", v.id)
    return vehicle(v)


@router.patch("/vehicles/{vehicle_id}/status")
def vehicle_status(vehicle_id: int, body: VehicleUpdate, user: User = Depends(require_roles(*OPS)), db: Session = Depends(get_db)):
    v = db.scalar(select(Vehicle).where(Vehicle.id == vehicle_id).with_for_update())
    if not v:
        raise HTTPException(404, "Vehicle not found")
    affected = []
    if body.status != "available":
        for r in db.scalars(select(Route).where(Route.vehicle_id == v.id, Route.status.in_(["planned", "active"])).with_for_update()):
            release_route(db, r, body.reason)
            affected.append(r.id)
        for d in db.scalars(select(Driver).where(Driver.vehicle_id == v.id, Driver.status.in_(["assigned", "on_trip"]))):
            d.status = "offline"
            d.online = False
    v.status = body.status
    if body.status in ("breakdown", "maintenance"):
        db.add(Alert(type=body.status, severity="high", message=f"{v.plate}: {body.reason}", entity_type="vehicle", entity_id=v.id))
    audit(db, user, "VEHICLE_STATUS", "vehicle", v.id, {"status": body.status, "released_routes": affected, "reason": body.reason})
    return {**vehicle(v), "released_routes": affected, "reoptimization_required": bool(affected)}


@router.get("/drivers")
def drivers(user: User = Depends(require_roles(*OPS, "driver")), db: Session = Depends(get_db)):
    query = select(Driver).order_by(Driver.id)
    if user.role == "driver":
        query = query.where(Driver.user_id == user.id)
    return [driver(d, private=user.role != "driver") for d in db.scalars(query)]


@router.post("/drivers", status_code=201)
def add_driver(body: DriverInput, user: User = Depends(require_roles("fleet_manager", "admin")), db: Session = Depends(get_db)):
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(409, "A user with this email already exists")
    if body.vehicle_id and not db.get(Vehicle, body.vehicle_id):
        raise HTTPException(404, "Vehicle not found")
    account = User(name=body.name, email=email, password_hash=hash_password(body.password), role="driver")
    db.add(account)
    db.flush()
    d = Driver(user_id=account.id, vehicle_id=body.vehicle_id, license_number=body.license_number, service=body.service,
               documents="Verified", lat=26.9124, lng=75.7873)
    db.add(d)
    db.flush()
    audit(db, user, "CREATE", "driver", d.id)
    return driver(d, private=True)


@router.get("/routes")
def routes(user: User = Depends(require_roles(*OPS, "driver")), db: Session = Depends(get_db)):
    query = select(Route).order_by(Route.id.desc()).limit(200)
    if user.role == "driver":
        d = db.scalar(select(Driver).where(Driver.user_id == user.id))
        query = query.where(Route.driver_id == d.id) if d else query.where(False)
    return [route(r) for r in db.scalars(query)]


@router.get("/maintenance")
def maintenance(user: User = Depends(require_roles(*OPS)), db: Session = Depends(get_db)):
    return [{"id": m.id, "vehicle_id": m.vehicle_id, "description": m.description, "scheduled_for": m.scheduled_for,
             "status": m.status, "cost": m.cost_paise / 100} for m in db.scalars(select(Maintenance).order_by(Maintenance.scheduled_for))]


@router.post("/maintenance", status_code=201)
def schedule_maintenance(body: MaintenanceInput, user: User = Depends(require_roles("fleet_manager", "admin")), db: Session = Depends(get_db)):
    if not db.get(Vehicle, body.vehicle_id):
        raise HTTPException(404, "Vehicle not found")
    if body.scheduled_for.tzinfo is None:
        raise HTTPException(422, "scheduled_for must include a timezone")
    m = Maintenance(**body.model_dump())
    db.add(m)
    db.flush()
    v = db.get(Vehicle, body.vehicle_id)
    v.next_maintenance = body.scheduled_for
    audit(db, user, "MAINTENANCE_SCHEDULE", "vehicle", v.id)
    return {"id": m.id, "status": m.status}
