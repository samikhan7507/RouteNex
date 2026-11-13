"""Order state machine and reservation expiry."""
from __future__ import annotations
import hashlib
import hmac

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.ratelimit import consume
from app.models import Alert, Driver, Order, Payment, Product, Route, User, utcnow
from app.services import payments
from app.services.common import audit, notify
from app.services.dispatch import close_route_if_done, release_route

FLOW = {"assigned": {"picked_up", "failed"}, "picked_up": {"out_for_delivery", "failed"}, "out_for_delivery": {"delivered", "failed"}}


def cancel(db: Session, user: User, order: Order, reason: str):
    db.scalar(select(User).where(User.id == order.user_id).with_for_update())
    order = db.scalar(select(Order).where(Order.id == order.id).with_for_update())
    if order.status in ("delivered", "cancelled", "failed"):
        raise HTTPException(409, "This order is already closed")
    if user.role == "customer" and order.status not in ("awaiting_payment", "placed", "assigned"):
        raise HTTPException(409, "This order is already on its way. Contact support for help")
    route = db.get(Route, order.route_id) if order.route_id else None
    if route and route.status in ("planned", "active"):
        release_route(db, route, f"Order #{order.id} cancelled: {reason}")
    for item in order.items:
        product = db.scalar(select(Product).where(Product.id == item.product_id).with_for_update())
        product.stock += item.quantity
        if order.status == "awaiting_payment":
            product.reserved -= item.quantity
    order.status, order.route_id, order.reservation_expires_at = "cancelled", None, None
    payment = db.scalar(select(Payment).where(Payment.purpose == "order", Payment.reference_id == order.id).with_for_update())
    if payment and payment.status == "captured":
        payments.refund(db, user, payment, payment.amount_paise, f"Order cancelled: {reason}")
    elif payment and payment.status == "created":
        payment.status, payment.failure_reason = "failed", "Order cancelled before collection"
        order.payment_status = "cancelled"
    else:
        order.payment_status = "cancelled"
    db.add(Alert(type="cancellation", severity="medium", message=f"Order #{order.id} cancelled; unfinished route work released for replanning", entity_type="order", entity_id=order.id))
    notify(db, order.user_id, "Order cancelled", "Stock has been released. Any eligible prepaid amount is returned to the original payment method.")
    audit(db, user, "CANCEL", "order", order.id, {"reason": reason})


def advance(db: Session, user: User, order: Order, status: str, code: str | None = None, reason: str = ""):
    order = db.scalar(select(Order).where(Order.id == order.id).with_for_update())
    driver = db.scalar(select(Driver).where(Driver.user_id == user.id)) if user.role == "driver" else None
    route = db.get(Route, order.route_id) if order.route_id else None
    if user.role == "driver" and (not driver or not route or route.driver_id != driver.id or route.status not in ("planned", "active")):
        raise HTTPException(403, "This order is not on your active route")
    if status not in FLOW.get(order.status, set()):
        raise HTTPException(409, f"Cannot move order from {order.status} to {status}")
    if status == "delivered":
        consume(db, f"delivery-proof:{order.id}", 5, 300, commit=True)
        if not order.delivery_otp_hash or not code or not hmac.compare_digest(order.delivery_otp_hash, hashlib.sha256(code.encode()).hexdigest()):
            raise HTTPException(400, "Incorrect delivery code. Ask the customer to check their order details")
        if order.payment_method == "cod":
            payments.settle_cash(db, "order", order)
    if status == "failed" and not reason:
        raise HTTPException(422, "A failure reason is required")
    order.status = status
    if route:
        if status == "picked_up" and route.status == "planned":
            route.status = "active"
        if status == "failed":
            release_route(db, route, f"Delivery #{order.id} failed: {reason}")
        else:
            close_route_if_done(db, route.id)
    if status == "delivered":
        notify(db, order.user_id, "Order delivered", f"Order #{order.id} was handed over successfully. Thank you for shopping with RouteNex.")
    audit(db, user, "ORDER_STATUS", "order", order.id, {"status": status, "reason": reason})


def tick(db: Session):
    now = utcnow()
    orders = list(db.scalars(select(Order).where(Order.status == "awaiting_payment", Order.reservation_expires_at < now).with_for_update()))
    for order in orders:
        payment = db.scalar(select(Payment).where(Payment.purpose == "order", Payment.reference_id == order.id).with_for_update())
        if payment and payment.status == "created":
            payments.fail(db, payment, "Checkout reservation expired")
        else:
            for item in order.items:
                product = db.scalar(select(Product).where(Product.id == item.product_id).with_for_update())
                product.stock += item.quantity
                product.reserved -= item.quantity
            order.status, order.payment_status, order.reservation_expires_at = "failed", "failed", None
