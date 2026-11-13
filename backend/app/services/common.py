from __future__ import annotations
from decimal import Decimal, InvalidOperation
from typing import Any
from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import AuditLog, Notification, User


def paise(rupees: Any) -> int:
    try:
        value = Decimal(str(rupees))
        if not value.is_finite() or value < 0 or value > Decimal("10000000") or value != value.quantize(Decimal("0.01")):
            raise ValueError
        return int(value * 100)
    except (InvalidOperation, ValueError):
        raise HTTPException(422, "Enter a valid amount with at most two decimal places")


def rupees(value: int) -> float:
    return value / 100


def audit(db: Session, actor: User | None, action: str, entity: str, entity_id: Any = "", details: dict | None = None, request: Request | None = None):
    db.add(AuditLog(actor_id=actor.id if actor else None, action=action, entity=entity, entity_id=str(entity_id),
                    details=details or {}, ip_address=request.client.host if request and request.client else "",
                    request_id=getattr(request.state, "request_id", "") if request else ""))


def notify(db: Session, user_id: int, title: str, body: str):
    db.add(Notification(user_id=user_id, title=title, body=body))


def locked(db: Session, model, object_id: int, owner_id: int | None = None):
    query = select(model).where(model.id == object_id).with_for_update()
    if owner_id is not None:
        query = query.where(model.user_id == owner_id)
    obj = db.scalar(query)
    if not obj:
        raise HTTPException(404, "Record not found")
    return obj


def conflict(message: str):
    raise HTTPException(409, message)
