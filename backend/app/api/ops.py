from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import current_user, require_roles
from app.db import get_db
from app.models import Alert, Driver, Notification, Order, Payment, Refund, Route, Trip, User, Vehicle
from app.schemas import ApplyPlan, EventInput, OptimizerInput
from app.services import dispatch
from app.services.common import audit, locked

router = APIRouter(prefix="/api", tags=["operations"])
OPS = ("dispatcher", "fleet_manager", "admin")


@router.post("/optimizer/preview")
def preview(body: OptimizerInput, user: User = Depends(require_roles(*OPS)), db: Session = Depends(get_db)):
    return dispatch.preview(db, user, body.model_dump())


@router.post("/optimizer/apply")
def apply(body: ApplyPlan, user: User = Depends(require_roles(*OPS)), db: Session = Depends(get_db)):
    return dispatch.apply(db, user, body.plan_id)


@router.get("/optimizer/summary")
def summary(user: User = Depends(require_roles(*OPS)), db: Session = Depends(get_db)):
    return {"pending_orders": db.scalar(select(func.count(Order.id)).where(Order.status == "placed", Order.route_id.is_(None))),
            "assigned_orders": db.scalar(select(func.count(Order.id)).where(Order.status.in_(["assigned", "picked_up", "out_for_delivery"]))),
            "available_vehicles": db.scalar(select(func.count(Vehicle.id)).where(Vehicle.status == "available")),
            "online_drivers": db.scalar(select(func.count(Driver.id)).where(Driver.online.is_(True), Driver.status == "available")),
            "active_routes": db.scalar(select(func.count(Route.id)).where(Route.status.in_(["planned", "active"]))),
            "open_alerts": db.scalar(select(func.count(Alert.id)).where(Alert.acknowledged.is_(False)))}


@router.get("/alerts")
def alerts(user: User = Depends(require_roles(*OPS)), db: Session = Depends(get_db)):
    rows = db.scalars(select(Alert).order_by(Alert.id.desc()).limit(100))
    return [{"id": a.id, "type": a.type, "severity": a.severity, "message": a.message, "entity_type": a.entity_type,
             "entity_id": a.entity_id, "acknowledged": a.acknowledged, "created_at": a.created_at} for a in rows]


@router.post("/alerts/{alert_id}/ack")
def ack(alert_id: int, user: User = Depends(require_roles(*OPS)), db: Session = Depends(get_db)):
    a = locked(db, Alert, alert_id)
    a.acknowledged = True
    audit(db, user, "ALERT_ACK", "alert", a.id)
    return {"acknowledged": True}


@router.post("/events")
def event(body: EventInput, user: User = Depends(require_roles(*OPS)), db: Session = Depends(get_db)):
    affected = []
    if body.event == "breakdown" and body.entity_type == "vehicle" and body.entity_id:
        v = db.scalar(select(Vehicle).where(Vehicle.id == body.entity_id).with_for_update())
        if not v:
            raise HTTPException(404, "Vehicle not found")
        v.status = "breakdown"
        for r in db.scalars(select(Route).where(Route.vehicle_id == v.id, Route.status.in_(["planned", "active"])).with_for_update()):
            dispatch.release_route(db, r, body.message)
            affected.append(r.id)
    a = Alert(type=body.event, severity="high" if body.event == "breakdown" else "medium", message=body.message,
              entity_type=body.entity_type, entity_id=body.entity_id)
    db.add(a)
    db.flush()
    audit(db, user, "OPS_EVENT", body.entity_type, body.entity_id or "", {"event": body.event, "released_routes": affected})
    return {"alert_id": a.id, "released_routes": affected, "reoptimization_required": bool(affected)}


@router.get("/notifications")
def notifications(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(Notification.id.desc()).limit(50))
    return [{"id": n.id, "title": n.title, "body": n.body, "read": n.read, "created_at": n.created_at} for n in rows]


@router.post("/notifications/{notification_id}/read")
def read_notification(notification_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = db.scalar(select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id))
    if not n:
        raise HTTPException(404, "Notification not found")
    n.read = True
    return {"read": True}


@router.get("/analytics")
def analytics(user: User = Depends(require_roles(*OPS)), db: Session = Depends(get_db)):
    captured = db.scalar(select(func.coalesce(func.sum(Payment.amount_paise), 0)).where(Payment.status.in_(["captured", "refund_pending", "refunded"]), Payment.purpose.in_(["order", "trip"])))
    refunds = db.scalar(select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(Refund.status.in_(["initiated", "processed"])))
    return {"revenue": max(0, captured - refunds) / 100, "gross_captured": captured / 100, "refunds": refunds / 100,
            "orders": db.scalar(select(func.count(Order.id))), "delivered_orders": db.scalar(select(func.count(Order.id)).where(Order.status == "delivered")),
            "completed_trips": db.scalar(select(func.count(Trip.id)).where(Trip.status == "completed")),
            "active_trips": db.scalar(select(func.count(Trip.id)).where(Trip.status.in_(["searching", "matched", "arrived", "started"]))),
            "vehicles": db.scalar(select(func.count(Vehicle.id))), "drivers": db.scalar(select(func.count(Driver.id))),
            "note": "Revenue excludes wallet top-ups and failed trips; initiated/processed refunds are deducted."}
