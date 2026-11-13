from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import current_user
from app.db import get_db
from app.models import Coupon, User, WalletTransaction, utcnow
from app.schemas import PaymentCreate
from app.services import payments
from app.services.coupons import evaluate
from pydantic import BaseModel, Field
from typing import Literal

router = APIRouter(prefix="/api", tags=["wallet and offers"])


class CouponValidate(BaseModel):
    code: str = Field(max_length=30)
    amount_paise: int = Field(gt=0, le=100000000)
    scope: Literal["shop", "ride", "parcel"]


@router.get("/wallet")
def wallet(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(WalletTransaction).where(WalletTransaction.user_id == user.id).order_by(WalletTransaction.id.desc()).limit(50))
    return {"balance": user.wallet_balance_paise / 100, "balance_paise": user.wallet_balance_paise,
            "transactions": [{"id": t.id, "amount": t.amount_paise / 100, "kind": t.kind, "note": t.note,
                              "balance_after": t.balance_after_paise / 100, "created_at": t.created_at} for t in rows]}


@router.post("/wallet/topup")
def topup(body: PaymentCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.purpose != "wallet_topup":
        raise HTTPException(422, "Use the payment checkout endpoint for purchases")
    return payments.create_checkout(db, user, "wallet_topup", None, body.idempotency_key, body.amount)


@router.get("/coupons")
def coupons(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Coupon).where(Coupon.active.is_(True)).order_by(Coupon.code))
    return [{"code": c.code, "title": c.title, "scope": c.scope, "kind": c.kind, "value": c.value,
             "max_discount": c.max_discount_paise / 100 if c.max_discount_paise else None,
             "min_amount": c.min_amount_paise / 100, "one_time": c.one_time, "expires_at": c.expires_at}
            for c in rows if not c.expires_at or c.expires_at > utcnow()]


@router.post("/coupons/validate")
def validate(body: CouponValidate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    discount, code = evaluate(db, user.id, body.code, body.amount_paise, body.scope)
    return {"valid": True, "code": code, "discount": discount / 100, "final": (body.amount_paise - discount) / 100}
