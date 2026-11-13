from __future__ import annotations
import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.security import current_user, protect_code, require_roles
from app.db import get_db
from app.models import Address, CartItem, Order, OrderItem, Product, Route, Driver, User, utcnow
from app.schemas import AddressInput, CancelInput, CartInput, CheckoutInput, ProofInput
from app.services import payments
from app.services.common import audit, locked
from app.services.coupons import evaluate, record
from app.services.orders import advance, cancel
from app.services.pricing import IST, delivery_fee
from app.services.serializers import address, order, product

router = APIRouter(prefix="/api", tags=["shop"])


@router.get("/products")
def products(q: str = Query("", max_length=100), category: str = Query("", max_length=80),
             sort: str = Query("popular", pattern="^(popular|price_asc|price_desc|name)$"),
             page: int = Query(1, ge=1), page_size: int = Query(24, ge=1, le=100), db: Session = Depends(get_db)):
    query = select(Product).where(Product.active.is_(True))
    count = select(func.count(Product.id)).where(Product.active.is_(True))
    if q:
        clause = or_(Product.name.ilike(f"%{q}%"), Product.description.ilike(f"%{q}%"), Product.category.ilike(f"%{q}%"))
        query, count = query.where(clause), count.where(clause)
    if category:
        query, count = query.where(Product.category == category), count.where(Product.category == category)
    ordering = {"popular": Product.id, "price_asc": Product.price_paise, "price_desc": Product.price_paise.desc(), "name": Product.name}[sort]
    total = db.scalar(count)
    rows = db.scalars(query.order_by(ordering).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [product(p) for p in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/products/{product_id}")
def product_detail(product_id: int, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if not p or not p.active:
        raise HTTPException(404, "Product not found")
    return product(p)


@router.get("/categories")
def categories(db: Session = Depends(get_db)):
    rows = db.execute(select(Product.category, func.count(Product.id)).where(Product.active.is_(True)).group_by(Product.category).order_by(Product.category)).all()
    return [{"name": name, "count": count} for name, count in rows]


@router.get("/addresses")
def addresses(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [address(a) for a in db.scalars(select(Address).where(Address.user_id == user.id).order_by(Address.id))]


@router.post("/addresses", status_code=201)
def add_address(body: AddressInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = Address(user_id=user.id, **body.model_dump())
    db.add(a)
    db.flush()
    audit(db, user, "CREATE", "address", a.id)
    return address(a)


@router.delete("/addresses/{address_id}")
def delete_address(address_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.scalar(select(Address).where(Address.id == address_id, Address.user_id == user.id))
    if not a:
        raise HTTPException(404, "Address not found")
    if db.scalar(select(Order.id).where(Order.address_id == address_id).limit(1)):
        raise HTTPException(409, "This address is used by an order and is kept for your records")
    db.delete(a)
    return {"deleted": True}


def cart_data(db: Session, user_id: int):
    items = list(db.scalars(select(CartItem).where(CartItem.user_id == user_id).order_by(CartItem.product_id)))
    lines = [{"product": product(i.product), "quantity": i.quantity, "line_total": i.product.price_paise * i.quantity / 100} for i in items]
    subtotal = sum(i.product.price_paise * i.quantity for i in items)
    fee = delivery_fee(subtotal) if items else 0
    return {"items": lines, "subtotal": subtotal / 100, "delivery_fee": fee / 100, "estimated_total": (subtotal + fee) / 100}


@router.get("/cart")
def get_cart(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return cart_data(db, user.id)


@router.put("/cart")
def set_cart(body: CartInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.get(Product, body.product_id)
    if not p or not p.active:
        raise HTTPException(404, "Product not found")
    item = db.get(CartItem, (user.id, body.product_id))
    if body.quantity == 0:
        if item:
            db.delete(item)
    elif item:
        item.quantity = body.quantity
    else:
        db.add(CartItem(user_id=user.id, product_id=body.product_id, quantity=body.quantity))
    db.flush()
    return cart_data(db, user.id)


@router.delete("/cart")
def clear_cart(user: User = Depends(current_user), db: Session = Depends(get_db)):
    for item in db.scalars(select(CartItem).where(CartItem.user_id == user.id)):
        db.delete(item)
    return cart_data(db, user.id)


@router.get("/orders")
def orders(kind: str = Query("", pattern="^(|active|history)$"), page: int = Query(1, ge=1),
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Order).options(selectinload(Order.items), selectinload(Order.address))
    if user.role == "customer":
        query = query.where(Order.user_id == user.id)
    elif user.role == "driver":
        driver = db.scalar(select(Driver).where(Driver.user_id == user.id))
        query = query.where(Order.route_id.in_(select(Route.id).where(Route.driver_id == driver.id))) if driver else query.where(False)
    if kind == "active":
        query = query.where(Order.status.in_(["awaiting_payment", "placed", "assigned", "picked_up", "out_for_delivery"]))
    rows = db.scalars(query.order_by(Order.id.desc()).offset((page - 1) * 50).limit(50)).all()
    return [order(o, user) for o in rows]


@router.get("/orders/{order_id}")
def order_detail(order_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    o = db.get(Order, order_id)
    if not o or (user.role == "customer" and o.user_id != user.id):
        raise HTTPException(404, "Order not found")
    if user.role == "driver":
        driver = db.scalar(select(Driver).where(Driver.user_id == user.id))
        if not driver or not o.route_id or db.get(Route, o.route_id).driver_id != driver.id:
            raise HTTPException(403, "This order is not assigned to you")
    data = order(o, user)
    if user.role == "driver" and get_settings().demo_mode:
        from app.core.security import reveal_code
        data["demo_delivery_otp"] = reveal_code(o.delivery_otp_encrypted)
    return data


@router.post("/orders", status_code=201)
def checkout(body: CheckoutInput, request: Request, user: User = Depends(require_roles("customer", "admin")), db: Session = Depends(get_db)):
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    existing = db.scalar(select(Order).where(Order.user_id == user.id, Order.idempotency_key == body.idempotency_key))
    if existing:
        return order(existing, user)
    now = utcnow()
    start, end = body.delivery_window_start.astimezone(IST), body.delivery_window_end.astimezone(IST)
    local_now = now.astimezone(IST)
    if end <= local_now or end > local_now + timedelta(days=7) or start.date() != end.date() or start < local_now.replace(hour=0, minute=0, second=0, microsecond=0):
        raise HTTPException(422, "Choose a delivery window within the next 7 days, on a single day")
    a = db.scalar(select(Address).where(Address.id == body.address_id, Address.user_id == user.id))
    if not a:
        raise HTTPException(404, "Delivery address not found")
    cart = list(db.scalars(select(CartItem).where(CartItem.user_id == user.id).order_by(CartItem.product_id)))
    if not cart:
        raise HTTPException(409, "Your basket is empty")
    lines, subtotal, weight = [], 0, 0
    for item in cart:
        p = db.scalar(select(Product).where(Product.id == item.product_id, Product.active.is_(True)).with_for_update())
        if not p or p.stock - p.reserved < item.quantity:
            raise HTTPException(409, f"Insufficient stock for {item.product.name}. Update your basket")
        p.stock -= item.quantity
        if body.payment_method == "razorpay":
            p.reserved += item.quantity
        subtotal += p.price_paise * item.quantity
        weight += p.weight_grams * item.quantity
        lines.append((p, item.quantity))
    discount, code = evaluate(db, user.id, body.coupon, subtotal, "shop")
    fee = delivery_fee(subtotal)
    total = subtotal - discount + fee
    otp = f"{secrets.randbelow(1_000_000):06d}"
    import hashlib
    o = Order(user_id=user.id, address_id=a.id, status="awaiting_payment" if body.payment_method == "razorpay" and total > 0 else "placed",
              subtotal_paise=subtotal, discount_paise=discount, delivery_fee_paise=fee, total_paise=total, coupon_code=code,
              payment_method=body.payment_method, payment_status="pending", priority=body.priority,
              delivery_window_start=body.delivery_window_start, delivery_window_end=body.delivery_window_end,
              delivery_otp_hash=hashlib.sha256(otp.encode()).hexdigest(), delivery_otp_encrypted=protect_code(otp),
              weight_grams=weight, idempotency_key=body.idempotency_key,
              reservation_expires_at=now + timedelta(minutes=get_settings().reservation_minutes) if body.payment_method == "razorpay" else None)
    db.add(o)
    db.flush()
    for p, quantity in lines:
        db.add(OrderItem(order_id=o.id, product_id=p.id, product_name=p.name, sku=p.sku, unit_price_paise=p.price_paise,
                         quantity=quantity, weight_grams=p.weight_grams))
    if o.status == "placed":
        payments.instant_payment(db, user, "order", o, body.payment_method)
    record(db, user.id, code, "order", o.id)
    for item in cart:
        db.delete(item)
    db.flush()
    db.refresh(o)
    audit(db, user, "CREATE", "order", o.id, {"total_paise": total, "payment_method": body.payment_method}, request)
    return order(o, user)


@router.post("/orders/{order_id}/cancel")
def cancel_order(order_id: int, body: CancelInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    o = locked(db, Order, order_id, user.id if user.role == "customer" else None)
    cancel(db, user, o, body.reason)
    return order(o, user)


@router.post("/orders/{order_id}/status")
def order_status(order_id: int, status: str = Query(pattern="^(picked_up|out_for_delivery|delivered|failed)$"),
                 reason: str = Query("", max_length=240),
                 body: ProofInput | None = None, user: User = Depends(require_roles("driver", "dispatcher", "admin")), db: Session = Depends(get_db)):
    o = locked(db, Order, order_id)
    advance(db, user, o, status, body.code if body else None, reason=reason)
    return order(o, user)
