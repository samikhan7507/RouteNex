from __future__ import annotations
from datetime import timedelta
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import require_roles
from app.db import get_db
from app.models import AuditLog, DriverEarning, LoginEvent, Order, Payment, Product, Trip, User, UserSession, utcnow
from app.schemas import ActiveInput, ProductInput, ProductUpdate, UserRoleInput
from app.services.common import audit, paise
from app.services.serializers import payment, product

router = APIRouter(prefix="/api/admin", tags=["administration"])


@router.get("/users")
def users(q: str = Query("", max_length=100), page: int = Query(1, ge=1), user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    query = select(User)
    if q:
        query = query.where(User.name.ilike(f"%{q}%") | User.email.ilike(f"%{q}%") | User.phone.ilike(f"%{q}%"))
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(User.id).offset((page - 1) * 50).limit(50)).all()
    return {"total": total, "items": [{"id": u.id, "name": u.name, "email": u.email, "phone": u.phone, "role": u.role,
             "active": u.active, "wallet_balance": u.wallet_balance_paise / 100, "created_at": u.created_at, "last_login_at": u.last_login_at} for u in rows]}


@router.patch("/users/{user_id}/active")
def set_active(user_id: int, body: ActiveInput, actor: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    target = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not target:
        raise HTTPException(404, "User not found")
    if target.id == actor.id and not body.active:
        raise HTTPException(409, "You cannot deactivate your own administrator account")
    if target.role == "admin" and not body.active and db.scalar(select(func.count(User.id)).where(User.role == "admin", User.active.is_(True))) <= 1:
        raise HTTPException(409, "At least one active administrator is required")
    target.active = body.active
    if not body.active:
        for s in db.scalars(select(UserSession).where(UserSession.user_id == target.id, UserSession.revoked_at.is_(None))):
            s.revoked_at = utcnow()
    audit(db, actor, "USER_ACTIVE", "user", target.id, {"active": body.active})
    return {"id": target.id, "active": target.active}


@router.patch("/users/{user_id}/role")
def set_role(user_id: int, body: UserRoleInput, actor: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    target = db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not target:
        raise HTTPException(404, "User not found")
    if target.id == actor.id and body.role != "admin":
        raise HTTPException(409, "You cannot remove your own administrator role")
    if target.role == "admin" and body.role != "admin" and db.scalar(select(func.count(User.id)).where(User.role == "admin", User.active.is_(True))) <= 1:
        raise HTTPException(409, "At least one active administrator is required")
    target.role = body.role
    for s in db.scalars(select(UserSession).where(UserSession.user_id == target.id, UserSession.revoked_at.is_(None))):
        s.revoked_at = utcnow()
    audit(db, actor, "USER_ROLE", "user", target.id, {"role": body.role})
    return {"id": target.id, "role": target.role, "sessions_revoked": True}


@router.get("/sessions")
def sessions(user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    now = utcnow()
    idle = now - timedelta(minutes=get_settings().session_idle_minutes)
    rows = db.execute(select(UserSession, User).join(User, UserSession.user_id == User.id)
                      .where(UserSession.revoked_at.is_(None), UserSession.expires_at > now, UserSession.last_seen_at > idle)
                      .order_by(UserSession.last_seen_at.desc()).limit(500)).all()
    return [{"session_id": s.id, "user_id": u.id, "name": u.name, "email": u.email, "phone": u.phone, "role": u.role,
             "ip_address": s.ip_address, "user_agent": s.user_agent, "login_at": s.created_at, "last_seen_at": s.last_seen_at,
             "expires_at": s.expires_at, "online": s.last_seen_at > now - timedelta(minutes=5)} for s, u in rows]


@router.delete("/sessions/{session_id}")
def revoke_session(session_id: str, actor: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    s = db.scalar(select(UserSession).where(UserSession.id == session_id).with_for_update())
    if not s:
        raise HTTPException(404, "Session not found")
    s.revoked_at = utcnow()
    audit(db, actor, "SESSION_REVOKE", "user_session", session_id, {"user_id": s.user_id})
    return {"revoked": True}


@router.get("/login-events")
def login_events(page: int = Query(1, ge=1), user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    rows = db.scalars(select(LoginEvent).order_by(LoginEvent.id.desc()).offset((page - 1) * 100).limit(100)).all()
    return [{"id": e.id, "email": e.email, "user_id": e.user_id, "success": e.success, "method": e.method,
             "reason": e.reason, "ip_address": e.ip_address, "user_agent": e.user_agent, "created_at": e.created_at} for e in rows]


@router.get("/audit")
def audit_logs(page: int = Query(1, ge=1), user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    rows = db.execute(select(AuditLog, User.name).join(User, AuditLog.actor_id == User.id, isouter=True).order_by(AuditLog.id.desc()).offset((page - 1) * 100).limit(100)).all()
    return [{"id": a.id, "actor_id": a.actor_id, "actor_name": name, "action": a.action, "entity": a.entity,
             "entity_id": a.entity_id, "details": a.details, "ip_address": a.ip_address, "request_id": a.request_id, "created_at": a.created_at} for a, name in rows]


@router.get("/overview")
def overview(user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    now = utcnow()
    active_sessions = db.scalar(select(func.count(UserSession.id)).where(UserSession.revoked_at.is_(None), UserSession.expires_at > now, UserSession.last_seen_at > now - timedelta(minutes=get_settings().session_idle_minutes)))
    active_users = db.scalar(select(func.count(func.distinct(UserSession.user_id))).where(UserSession.revoked_at.is_(None), UserSession.expires_at > now, UserSession.last_seen_at > now - timedelta(minutes=get_settings().session_idle_minutes)))
    dau = db.scalar(select(func.count(func.distinct(UserSession.user_id))).where(UserSession.created_at > now - timedelta(days=1)))
    return {"users": db.scalar(select(func.count(User.id))), "active_users": active_users, "active_sessions": active_sessions,
            "daily_active_users": dau, "products": db.scalar(select(func.count(Product.id)).where(Product.active.is_(True))),
            "orders_today": db.scalar(select(func.count(Order.id)).where(Order.created_at > now - timedelta(days=1))),
            "trips_today": db.scalar(select(func.count(Trip.id)).where(Trip.created_at > now - timedelta(days=1)))}


@router.get("/payments")
def payments(page: int = Query(1, ge=1), user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    rows = db.scalars(select(Payment).order_by(Payment.id.desc()).offset((page - 1) * 100).limit(100)).all()
    return [payment(p) for p in rows]


@router.get("/products")
def products(user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    return [product(p) for p in db.scalars(select(Product).order_by(Product.id))]


@router.post("/products", status_code=201)
def add_product(body: ProductInput, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    data = body.model_dump()
    data["price_paise"] = paise(data.pop("price"))
    sku = "RN-C" + secrets.token_hex(4).upper()
    p = Product(sku=sku, slug=sku.lower(), image_credit="Operator supplied", **data)
    db.add(p)
    db.flush()
    audit(db, user, "CREATE", "product", p.id)
    return product(p)


@router.patch("/products/{product_id}")
def update_product(product_id: int, body: ProductUpdate, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    p = db.scalar(select(Product).where(Product.id == product_id).with_for_update())
    if not p:
        raise HTTPException(404, "Product not found")
    if body.price is not None:
        p.price_paise = paise(body.price)
    if body.stock is not None:
        if body.stock < p.reserved:
            raise HTTPException(409, "Stock cannot be lower than units reserved by pending checkouts")
        p.stock = body.stock
    if body.active is not None:
        p.active = body.active
    audit(db, user, "PRODUCT_UPDATE", "product", p.id, body.model_dump(mode="json"))
    return product(p)


@router.get("/settlements")
def settlements(user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    rows = db.scalars(select(DriverEarning).order_by(DriverEarning.id.desc()).limit(200)).all()
    return [{"id": e.id, "driver_id": e.driver_id, "trip_id": e.trip_id, "gross": e.gross_paise / 100,
             "platform_fee": e.platform_fee_paise / 100, "net": e.net_paise / 100, "status": e.status,
             "settlement_reference": e.settlement_reference, "created_at": e.created_at, "paid_at": e.paid_at} for e in rows]


@router.post("/settlements/{earning_id}/mark-paid")
def mark_settlement(earning_id: int, reference: str = Query(min_length=3, max_length=120), user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    e = db.scalar(select(DriverEarning).where(DriverEarning.id == earning_id).with_for_update())
    if not e:
        raise HTTPException(404, "Earning not found")
    if e.status == "paid":
        raise HTTPException(409, "Settlement is already recorded")
    e.status, e.settlement_reference, e.paid_at = "paid", reference, utcnow()
    audit(db, user, "SETTLEMENT_PAID", "driver_earning", e.id, {"reference": reference, "net_paise": e.net_paise})
    return {"id": e.id, "status": "paid", "note": "Offline settlement recorded; no bank transfer was initiated by this action"}
