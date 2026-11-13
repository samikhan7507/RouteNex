"""Grounded operations assistant. Destructive/dispatch actions require explicit confirmation."""
from __future__ import annotations
import re
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import current_user
from app.db import get_db
from app.models import Alert, AssistantAction, Order, Trip, User, utcnow
from app.schemas import AssistantConfirm, AssistantInput
from app.services import dispatch
from app.services.common import audit, locked
from app.services.orders import cancel

router = APIRouter(prefix="/api/assistant", tags=["assistant"])
OPS = ("dispatcher", "fleet_manager", "admin")


def _summary(db: Session, user: User) -> str:
    if user.role in OPS:
        pending = db.scalar(select(func.count(Order.id)).where(Order.status == "placed"))
        active = db.scalar(select(func.count(Trip.id)).where(Trip.status.in_(["searching", "matched", "arrived", "started"])))
        alerts = db.scalar(select(func.count(Alert.id)).where(Alert.acknowledged.is_(False)))
        return f"Current operations: {pending} orders awaiting dispatch, {active} active trips, {alerts} open alerts. Say 'plan routes' to prepare a reviewable dispatch preview."
    orders = db.scalar(select(func.count(Order.id)).where(Order.user_id == user.id, Order.status.in_(["placed", "assigned", "picked_up", "out_for_delivery"])))
    trips = db.scalar(select(func.count(Trip.id)).where(Trip.user_id == user.id, Trip.status.in_(["searching", "matched", "arrived", "started"])))
    return f"You have {orders} active orders and {trips} active trips. Your wallet balance is ₹{user.wallet_balance_paise / 100:.2f}. I can help you track or cancel an order before it is on its way."


@router.post("/message")
def message(body: AssistantInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    text = body.message.lower().strip()
    if any(w in text for w in ("summary", "status", "overview", "help")):
        return {"reply": _summary(db, user), "action": None}
    if re.search(r"plan|optimi[sz]e|dispatch", text) and user.role in OPS:
        action = AssistantAction(user_id=user.id, tool="preview_routes", args={}, summary="Generate a route preview for all eligible pending orders. Nothing is assigned until a dispatcher applies it in Route planning.", expires_at=utcnow() + timedelta(minutes=10))
        db.add(action)
        db.flush()
        return {"reply": "I can prepare a route preview. Confirm below; applying the plan remains a separate, explicit step in Route planning.", "action": {"id": action.id, "summary": action.summary}}
    match = re.search(r"cancel\s+(?:order\s*)?#?(\d+)", text)
    if match:
        oid = int(match.group(1))
        order = db.get(Order, oid)
        if not order or (user.role == "customer" and order.user_id != user.id):
            raise HTTPException(404, "Order not found")
        action = AssistantAction(user_id=user.id, tool="cancel_order", args={"order_id": oid}, summary=f"Cancel order #{oid}, release stock and refund any eligible prepaid amount to the original payment method.", expires_at=utcnow() + timedelta(minutes=10))
        db.add(action)
        db.flush()
        return {"reply": f"Please confirm cancellation of order #{oid}.", "action": {"id": action.id, "summary": action.summary}}
    return {"reply": "I can show your current status, prepare a route preview (operations roles), or cancel an eligible order. Try 'summary', 'plan routes', or 'cancel order 12'. I do not invent bookings or payment confirmations.", "action": None}


@router.post("/confirm")
def confirm(body: AssistantConfirm, user: User = Depends(current_user), db: Session = Depends(get_db)):
    action = db.scalar(select(AssistantAction).where(AssistantAction.id == body.action_id, AssistantAction.user_id == user.id).with_for_update())
    if not action or action.status != "pending" or action.expires_at <= utcnow():
        raise HTTPException(409, "This confirmation expired or was already used")
    if action.tool == "preview_routes":
        if user.role not in OPS:
            raise HTTPException(403, "Operations permission required")
        result = dispatch.preview(db, user, {"traffic_factor": 1.0, "time_limit_seconds": 1.5})
        text = f"Preview {result['plan_id']} created with {len(result['routes'])} routes. Review and apply it in Route planning."
    elif action.tool == "cancel_order":
        order = locked(db, Order, action.args["order_id"], user.id if user.role == "customer" else None)
        cancel(db, user, order, "Cancelled through assistant after explicit confirmation")
        text = f"Order #{order.id} cancelled."
    else:
        raise HTTPException(400, "Unknown assistant action")
    action.status, action.result = "confirmed", text
    audit(db, user, "ASSISTANT_CONFIRM", "assistant_action", action.id, {"tool": action.tool})
    return {"reply": text, "action_id": action.id}


@router.post("/dismiss")
def dismiss(body: AssistantConfirm, user: User = Depends(current_user), db: Session = Depends(get_db)):
    action = db.scalar(select(AssistantAction).where(AssistantAction.id == body.action_id, AssistantAction.user_id == user.id).with_for_update())
    if not action or action.status != "pending":
        raise HTTPException(409, "No pending action to dismiss")
    action.status = "dismissed"
    return {"dismissed": True}
