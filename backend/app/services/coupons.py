"""Coupon validation. Call while the purchasing user's row is locked."""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import Coupon, CouponUse, utcnow


def evaluate(db: Session, user_id: int, code: str | None, subtotal: int, scope: str) -> tuple[int, str | None]:
    if not code:
        return 0, None
    coupon = db.scalar(select(Coupon).where(Coupon.code == code.upper().strip()).with_for_update())
    if not coupon or not coupon.active or (coupon.expires_at and coupon.expires_at <= utcnow()):
        raise HTTPException(422, "This offer is not available")
    if coupon.scope not in ("all", scope) or subtotal < coupon.min_amount_paise:
        raise HTTPException(422, f"This offer requires a minimum eligible amount of ₹{coupon.min_amount_paise / 100:.0f}")
    if coupon.one_time and db.scalar(select(CouponUse.id).where(CouponUse.coupon_code == coupon.code, CouponUse.user_id == user_id).limit(1)):
        raise HTTPException(422, "You have already used this offer")
    discount = subtotal * coupon.value // 100 if coupon.kind == "percent" else coupon.value
    if coupon.max_discount_paise is not None:
        discount = min(discount, coupon.max_discount_paise)
    return min(subtotal, discount), coupon.code


def record(db: Session, user_id: int, code: str | None, ref_type: str, ref_id: int):
    if code:
        db.add(CouponUse(coupon_code=code, user_id=user_id, ref_type=ref_type, ref_id=ref_id))
