"""Payment orchestration: never trust browser success, never capture twice.

Razorpay Orders + Checkout; server-side signature AND payment retrieval/capture.
Webhook events are signature-checked and deduplicated in the same DB transaction.
Demo payments are a separate, explicitly labelled provider and cannot run in prod.
"""
from __future__ import annotations
import hashlib
import hmac
import json

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (Alert, Order, OrderItem, Payment, Product, Refund, Trip, User,
                        WalletTransaction, WebhookEvent, utcnow)
from app.services.common import audit, notify, paise


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    s = get_settings()
    try:
        r = httpx.request(method, s.razorpay_api_url.rstrip("/") + path, json=payload,
                          auth=(s.razorpay_key_id, s.razorpay_key_secret), timeout=10.0,
                          headers={"User-Agent": "RouteNex/3.0"})
        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as exc:
        # Provider body may contain sensitive data; do not log or return it.
        raise HTTPException(502, f"Payment provider rejected the request (HTTP {exc.response.status_code}). Please contact support if money was debited")
    except (httpx.HTTPError, ValueError):
        raise HTTPException(503, "Payment provider is temporarily unreachable. Do not retry a debited payment; check its status first")


def wallet_entry(db: Session, user: User, amount: int, kind: str, note: str, payment_id: int | None = None):
    user.wallet_balance_paise += amount
    if user.wallet_balance_paise < 0:
        raise HTTPException(409, "Insufficient wallet balance")
    db.add(WalletTransaction(user_id=user.id, payment_id=payment_id, amount_paise=amount, kind=kind,
                             balance_after_paise=user.wallet_balance_paise, note=note))


def _reference(db: Session, user: User, purpose: str, reference_id: int | None):
    if purpose == "wallet_topup":
        return None
    model = Order if purpose == "order" else Trip
    ref = db.scalar(select(model).where(model.id == reference_id, model.user_id == user.id).with_for_update())
    if not ref:
        raise HTTPException(404, "Purchase not found")
    if ref.status != "awaiting_payment":
        raise HTTPException(409, "This purchase is not awaiting payment")
    return ref


def create_checkout(db: Session, user: User, purpose: str, reference_id: int | None, key: str, topup_amount=None) -> dict:
    settings = get_settings()
    # Serialize a user's checkout/top-up operations, including coupon and wallet use.
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    existing = db.scalar(select(Payment).where(Payment.user_id == user.id, Payment.idempotency_key == key))
    if existing:
        if existing.purpose != purpose or existing.reference_id != reference_id:
            raise HTTPException(409, "Idempotency key was used for a different purchase")
        return checkout_data(existing)
    ref = _reference(db, user, purpose, reference_id)
    amount = paise(topup_amount) if purpose == "wallet_topup" else ref.total_paise
    if amount <= 0:
        raise HTTPException(422, "Payment amount must be positive")
    payment = Payment(user_id=user.id, purpose=purpose, reference_id=reference_id, provider=settings.payment_provider,
                      amount_paise=amount, idempotency_key=key, receipt="")
    db.add(payment)
    db.flush()
    payment.receipt = "rn_" + payment.public_id.replace("-", "")
    if settings.payment_provider == "demo":
        payment.provider_order_id = "demo_order_" + payment.public_id.replace("-", "")
    else:
        order = _request("POST", "/orders", {"amount": amount, "currency": "INR", "receipt": payment.receipt,
                                            "notes": {"purpose": purpose, "reference_id": str(reference_id or ""), "payment_public_id": payment.public_id}})
        if order.get("amount") != amount or order.get("currency") != "INR" or not order.get("id"):
            raise HTTPException(502, "Payment provider returned an invalid order")
        payment.provider_order_id = order["id"]
    audit(db, user, "PAYMENT_CREATED", "payment", payment.public_id, {"purpose": purpose, "amount_paise": amount, "provider": payment.provider})
    return checkout_data(payment)


def checkout_data(payment: Payment) -> dict:
    s = get_settings()
    return {"id": payment.public_id, "provider": payment.provider, "status": payment.status,
            "amount_paise": payment.amount_paise, "amount": payment.amount_paise / 100, "currency": "INR",
            "key_id": s.razorpay_key_id if payment.provider == "razorpay" else "",
            "provider_order_id": payment.provider_order_id, "purpose": payment.purpose, "reference_id": payment.reference_id,
            "demo": payment.provider == "demo", "receipt": payment.receipt}


def _release(db: Session, ref: Order | Trip):
    if isinstance(ref, Order):
        for item in db.scalars(select(OrderItem).where(OrderItem.order_id == ref.id)):
            product = db.scalar(select(Product).where(Product.id == item.product_id).with_for_update())
            product.stock += item.quantity
            product.reserved -= item.quantity
        ref.status, ref.payment_status, ref.reservation_expires_at = "failed", "failed", None
    else:
        ref.status, ref.payment_status = "expired", "failed"
    notify(db, ref.user_id, "Payment not completed", "Your reservation was released. No payment was recorded by RouteNex.")


def _fulfill(db: Session, payment: Payment):
    if payment.purpose == "wallet_topup":
        wallet_entry(db, db.get(User, payment.user_id), payment.amount_paise, "topup", "Verified wallet top-up", payment.id)
        notify(db, payment.user_id, "Wallet topped up", f"₹{payment.amount_paise / 100:.2f} is now available in your wallet.")
        return
    model = Order if payment.purpose == "order" else Trip
    ref = db.scalar(select(model).where(model.id == payment.reference_id).with_for_update())
    if ref.status != "awaiting_payment":
        # A late provider confirmation must return money, not resurrect released stock.
        refund(db, None, payment, payment.amount_paise, "Purchase expired before payment confirmation; automatic refund")
        return
    if payment.purpose == "order":
        for item in db.scalars(select(OrderItem).where(OrderItem.order_id == ref.id)):
            product = db.scalar(select(Product).where(Product.id == item.product_id).with_for_update())
            product.reserved -= item.quantity
        ref.status, ref.reservation_expires_at = "placed", None
    else:
        ref.status, ref.search_started_at = "searching", utcnow()
    ref.payment_status = "paid"
    notify(db, ref.user_id, "Payment received", f"Your {'order' if payment.purpose == 'order' else 'trip'} #{ref.id} is confirmed.")


def capture(db: Session, payment: Payment, provider_payment_id: str, method: str = "") -> dict:
    db.scalar(select(User).where(User.id == payment.user_id).with_for_update())
    payment = db.scalar(select(Payment).where(Payment.id == payment.id).with_for_update())
    if payment.status == "captured":
        return checkout_data(payment)
    if payment.status not in ("created", "authorized"):
        raise HTTPException(409, "This payment can no longer be completed")
    if payment.provider == "demo":
        if not get_settings().demo_mode:
            raise HTTPException(403, "Demo payments are disabled")
    else:
        remote = _request("GET", "/payments/" + provider_payment_id)
        if remote.get("order_id") != payment.provider_order_id or remote.get("amount") != payment.amount_paise or remote.get("currency") != "INR":
            raise HTTPException(400, "Payment does not match this purchase")
        if remote.get("status") == "authorized":
            remote = _request("POST", f"/payments/{provider_payment_id}/capture", {"amount": payment.amount_paise, "currency": "INR"})
        if remote.get("status") != "captured":
            raise HTTPException(409, "Payment is not captured yet. Check again shortly")
    payment.status, payment.provider_payment_id, payment.method = "captured", provider_payment_id, method
    payment.captured_at = utcnow()
    _fulfill(db, payment)
    audit(db, None, "PAYMENT_CAPTURED", "payment", payment.public_id, {"amount_paise": payment.amount_paise, "provider": payment.provider})
    db.flush()
    return checkout_data(payment)


def verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    expected = hmac.new(get_settings().razorpay_key_secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def fail(db: Session, payment: Payment, reason: str = "Payment failed"):
    db.scalar(select(User).where(User.id == payment.user_id).with_for_update())
    payment = db.scalar(select(Payment).where(Payment.id == payment.id).with_for_update())
    if payment.status == "captured":
        return
    if payment.status != "created":
        return
    payment.status, payment.failure_reason = "failed", reason[:240]
    if payment.purpose != "wallet_topup":
        model = Order if payment.purpose == "order" else Trip
        ref = db.scalar(select(model).where(model.id == payment.reference_id).with_for_update())
        if ref.status == "awaiting_payment":
            _release(db, ref)


def instant_payment(db: Session, user: User, purpose: str, ref: Order | Trip, method: str):
    """Wallet/cash tender is recorded atomically with purchase creation."""
    if ref.total_paise == 0:
        ref.payment_status = "paid"
        return None
    provider = "wallet" if method == "wallet" else "cash"
    payment = Payment(user_id=user.id, purpose=purpose, reference_id=ref.id, provider=provider,
                      amount_paise=ref.total_paise, idempotency_key=f"{provider}-{purpose}-{ref.id}",
                      receipt=f"rn_{provider}_{purpose}_{ref.id}", method=method,
                      status="captured" if provider == "wallet" else "created",
                      captured_at=utcnow() if provider == "wallet" else None)
    db.add(payment)
    db.flush()
    if provider == "wallet":
        wallet_entry(db, user, -ref.total_paise, "purchase", f"Payment for {purpose} #{ref.id}", payment.id)
        ref.payment_status = "paid"
    return payment


def settle_cash(db: Session, purpose: str, ref: Order | Trip):
    if ref.total_paise == 0:
        ref.payment_status = "paid"
        return
    payment = db.scalar(select(Payment).where(Payment.purpose == purpose, Payment.reference_id == ref.id, Payment.provider == "cash").with_for_update())
    if not payment or payment.status not in ("created", "captured"):
        raise HTTPException(409, "Cash payment cannot be settled")
    if payment.status != "captured":
        payment.status, payment.captured_at, payment.method = "captured", utcnow(), "cash"
    ref.payment_status = "paid"
    audit(db, None, "CASH_COLLECTED", "payment", payment.public_id, {"amount_paise": payment.amount_paise, "reference_id": ref.id})


def process_webhook(db: Session, raw: bytes, signature: str, event_id: str) -> dict:
    settings = get_settings()
    if settings.payment_provider != "razorpay":
        raise HTTPException(409, "Razorpay webhooks are not enabled")
    expected = hmac.new(settings.razorpay_webhook_secret.encode(), raw, hashlib.sha256).hexdigest()
    if not signature or not hmac.compare_digest(expected, signature):
        raise HTTPException(400, "Invalid webhook signature")
    try:
        body = json.loads(raw)
        event_type = body["event"]
        entity = body["payload"]["payment"]["entity"]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "Invalid webhook payload")
    event_id = (event_id or hashlib.sha256(raw).hexdigest())[:120]
    if db.scalar(select(WebhookEvent.id).where(WebhookEvent.provider == "razorpay", WebhookEvent.event_id == event_id)):
        return {"received": True, "duplicate": True}
    event = WebhookEvent(provider="razorpay", event_id=event_id, event_type=event_type, payload=body)
    db.add(event)
    db.flush()
    if event_type == "refund.processed":
        refund_entity = body.get("payload", {}).get("refund", {}).get("entity", {})
        refund = db.scalar(select(Refund).where(Refund.provider_refund_id == refund_entity.get("id")).with_for_update())
        if refund:
            payment = db.scalar(select(Payment).where(Payment.id == refund.payment_id).with_for_update())
            refund.status, refund.processed_at = "processed", utcnow()
            total = db.scalar(select(func.coalesce(func.sum(Refund.amount_paise), 0)).where(Refund.payment_id == payment.id, Refund.status.in_(["initiated", "processed"])))
            payment.status = "refunded" if total >= payment.amount_paise else "captured"
            if payment.purpose != "wallet_topup":
                model = Order if payment.purpose == "order" else Trip
                ref = db.get(model, payment.reference_id)
                ref.payment_status = payment.status
            notify(db, payment.user_id, "Refund processed", f"₹{refund.amount_paise / 100:.2f} has been sent back to the original payment method.")
    else:
        payment = db.scalar(select(Payment).where(Payment.provider_order_id == entity.get("order_id")).with_for_update())
        if not payment:
            event.status = "ignored"
        elif entity.get("amount") != payment.amount_paise or entity.get("currency") != "INR":
            raise HTTPException(400, "Webhook amount/currency mismatch")
        elif event_type in ("payment.captured", "order.paid"):
            if payment.status in ("created", "authorized"):
                capture(db, payment, entity["id"], entity.get("method", ""))
            elif payment.status == "failed" and entity.get("status") == "captured":
                # Late capture after local expiry: reconcile by refunding the original method.
                payment.status, payment.provider_payment_id, payment.captured_at = "captured", entity["id"], utcnow()
                refund(db, None, payment, payment.amount_paise, "Late capture after reservation expiry; automatic refund")
                db.add(Alert(type="payment_reconciliation", severity="high", message=f"Late capture refunded for payment {payment.public_id}", entity_type="payment", entity_id=payment.id))
        elif event_type == "payment.failed" and payment.status == "created":
            fail(db, payment, "Provider reported a failed payment")
    event.status, event.processed_at = "processed", utcnow()
    return {"received": True, "duplicate": False}


def refund(db: Session, user: User | None, payment: Payment, amount: int, reason: str, cash_returned: bool = False):
    db.scalar(select(User).where(User.id == payment.user_id).with_for_update())
    payment = db.scalar(select(Payment).where(Payment.id == payment.id).with_for_update())
    if payment.status != "captured":
        raise HTTPException(409, "Only a captured, unrefunded payment can be refunded")
    if amount <= 0 or amount > payment.amount_paise:
        raise HTTPException(422, "Refund must be positive and cannot exceed the payment")
    if payment.provider == "cash" and not cash_returned:
        raise HTTPException(422, "Confirm that cash was physically returned before recording this refund")
    row = Refund(payment_id=payment.id, amount_paise=amount, reason=reason)
    db.add(row)
    db.flush()
    if payment.provider == "razorpay":
        remote = _request("POST", f"/payments/{payment.provider_payment_id}/refund", {"amount": amount, "notes": {"reason": reason, "refund_id": str(row.id)}})
        row.provider_refund_id = remote["id"]
        row.status = "processed" if remote.get("status") == "processed" else "initiated"
    else:
        row.status, row.processed_at, row.provider_refund_id = "processed", utcnow(), f"{payment.provider}_refund_{row.id}"
        if payment.provider == "wallet":
            wallet_entry(db, db.get(User, payment.user_id), amount, "refund", reason, payment.id)
    payment.status = "refunded" if row.status == "processed" else "refund_pending"
    if payment.purpose != "wallet_topup":
        model = Order if payment.purpose == "order" else Trip
        ref = db.get(model, payment.reference_id)
        ref.payment_status = payment.status
    if row.status == "processed":
        notify(db, payment.user_id, "Refund processed", f"₹{amount / 100:.2f} returned to the original payment method.")
    audit(db, user, "REFUND", "payment", payment.public_id, {"amount_paise": amount, "reason": reason, "status": row.status})
    return {"id": row.id, "status": row.status, "amount": amount / 100, "destination": "original payment method"}
