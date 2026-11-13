from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ratelimit import consume
from app.core.security import current_user, require_roles
from app.db import get_db
from app.models import Payment, User
from app.schemas import DemoPaymentInput, PaymentCreate, PaymentVerify, RefundInput
from app.services import payments
from app.services.common import paise
from app.services.serializers import payment

router = APIRouter(prefix="/api/payments", tags=["payments"])


@router.post("/checkout", status_code=201)
def checkout(body: PaymentCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    consume(db, f"checkout:{user.id}", 10, 60, commit=True)
    return payments.create_checkout(db, user, body.purpose, body.reference_id, body.idempotency_key, body.amount)


@router.get("")
def history(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Payment).where(Payment.user_id == user.id).order_by(Payment.id.desc()).limit(100))
    return [payment(p) for p in rows]


@router.get("/{public_id}")
def detail(public_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.scalar(select(Payment).where(Payment.public_id == public_id, Payment.user_id == user.id))
    if not p:
        raise HTTPException(404, "Payment not found")
    return payment(p)


@router.post("/verify")
def verify(body: PaymentVerify, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = db.scalar(select(Payment).where(Payment.provider_order_id == body.razorpay_order_id, Payment.user_id == user.id))
    if not p or p.provider != "razorpay":
        raise HTTPException(404, "Payment not found")
    if not payments.verify_signature(body.razorpay_order_id, body.razorpay_payment_id, body.razorpay_signature):
        raise HTTPException(400, "Payment signature verification failed")
    return payments.capture(db, p, body.razorpay_payment_id)


@router.post("/{public_id}/demo")
def demo_result(public_id: str, body: DemoPaymentInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not get_settings().demo_mode:
        raise HTTPException(403, "Demo payments are disabled")
    p = db.scalar(select(Payment).where(Payment.public_id == public_id, Payment.user_id == user.id, Payment.provider == "demo"))
    if not p:
        raise HTTPException(404, "Demo payment not found")
    if body.outcome == "failure":
        payments.fail(db, p, "Simulated payment failure")
        return payment(p)
    return payments.capture(db, p, "demo_pay_" + p.public_id.replace("-", ""), "demo")


@router.post("/webhooks/razorpay")
async def webhook(request: Request, db: Session = Depends(get_db)):
    raw = await request.body()
    if len(raw) > 1_000_000:
        raise HTTPException(413, "Webhook payload too large")
    return payments.process_webhook(db, raw, request.headers.get("x-razorpay-signature", ""), request.headers.get("x-razorpay-event-id", ""))


@router.post("/{public_id}/refund")
def refund(public_id: str, body: RefundInput, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)):
    p = db.scalar(select(Payment).where(Payment.public_id == public_id))
    if not p:
        raise HTTPException(404, "Payment not found")
    amount = paise(body.amount) if body.amount is not None else p.amount_paise
    return payments.refund(db, user, p, amount, body.reason, cash_returned=body.cash_returned)
