import sqlite3
from fastapi import APIRouter, Depends, HTTPException
from db import rows, one, run, audit
from deps import roles
from schemas import VehicleIn, DriverIn, StatusIn

router = APIRouter(prefix="/api", tags=["fleet"])
VEHICLE_STATUSES = {"available", "assigned", "maintenance", "breakdown", "retired"}


@router.get("/vehicles")
def vehicles(u=Depends(roles("driver", "dispatcher", "fleet_manager", "admin"))):
    if u["role"] == "driver":   # a driver only sees their own vehicle
        return rows("SELECT * FROM vehicles WHERE id=(SELECT vehicle_id FROM drivers WHERE user_id=?)", (u["id"],))
    return rows("SELECT * FROM vehicles ORDER BY id")


@router.post("/vehicles")
def vehicle_add(x: VehicleIn, u=Depends(roles("fleet_manager", "admin"))):
    try:
        i = run("INSERT INTO vehicles(plate,type,capacity_kg,lat,lng,documents,next_maintenance,cost_per_km) VALUES(?,?,?,?,?,?,?,?)",
                (x.plate.strip().upper(), x.type, x.capacity_kg, x.lat, x.lng, x.documents, x.next_maintenance, x.cost_per_km))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Vehicle plate exists")
    audit(u["id"], "CREATE", "vehicle", i)
    return one("SELECT * FROM vehicles WHERE id=?", (i,))


@router.patch("/vehicles/{vid}/status")
def vehicle_status(vid: int, x: StatusIn, u=Depends(roles("fleet_manager", "dispatcher", "admin"))):
    if x.status not in VEHICLE_STATUSES:
        raise HTTPException(400, f"Status must be one of: {', '.join(sorted(VEHICLE_STATUSES))}")
    if not one("SELECT 1 FROM vehicles WHERE id=?", (vid,)):
        raise HTTPException(404, "Vehicle not found")
    run("UPDATE vehicles SET status=?,available=? WHERE id=?", (x.status, 1 if x.status == "available" else 0, vid))
    audit(u["id"], "STATUS", "vehicle", vid, x.status)
    return one("SELECT * FROM vehicles WHERE id=?", (vid,))


@router.get("/drivers")
def drivers(u=Depends(roles("driver", "dispatcher", "fleet_manager", "admin"))):
    q = "SELECT d.*,u.name,u.phone,v.plate FROM drivers d JOIN users u ON u.id=d.user_id LEFT JOIN vehicles v ON v.id=d.vehicle_id"
    return rows(q + " WHERE d.user_id=?", (u["id"],)) if u["role"] == "driver" else rows(q)


@router.post("/drivers")
def driver_add(x: DriverIn, u=Depends(roles("fleet_manager", "admin"))):
    usr = one("SELECT role FROM users WHERE id=?", (x.user_id,))
    if not usr or usr["role"] != "driver":
        raise HTTPException(400, "user_id must belong to a user with role 'driver'")
    if x.vehicle_id is not None and not one("SELECT 1 FROM vehicles WHERE id=?", (x.vehicle_id,)):
        raise HTTPException(400, "Vehicle not found")
    try:
        i = run("INSERT INTO drivers(user_id,license,vehicle_id,lat,lng,documents,capacity_rating) VALUES(?,?,?,?,?,?,5)",
                (x.user_id, x.license, x.vehicle_id, x.lat, x.lng, x.documents))
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Driver profile already exists for this user")
    audit(u["id"], "CREATE", "driver", i)
    return one("SELECT * FROM drivers WHERE id=?", (i,))
