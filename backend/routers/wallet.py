from fastapi import APIRouter, Depends
from db import rows, one, tx, audit
from deps import current
from schemas import TopupIn, CouponIn
from services import trips
from services.errors import ApiError

router = APIRouter(prefix="/api", tags=["wallet"])


@router.get("/wallet")
def wallet(u=Depends(current)):
    return {"balance": one("SELECT wallet_balance b FROM users WHERE id=?", (u["id"],))["b"],
            "txns": rows("SELECT amount,kind,note,balance_after,created_at FROM wallet_txns WHERE user_id=? ORDER BY id DESC LIMIT 30", (u["id"],))}


@router.post("/wallet/topup")
def topup(x: TopupIn, u=Depends(current)):
    # DEMO: simulates a successful UPI collect. A real PSP (Razorpay etc.) would confirm via webhook before crediting.
    with tx() as c:
        trips.wallet_credit(c, u["id"], float(x.amount), "topup", "Wallet top-up (demo UPI)")
        bal = c.execute("SELECT wallet_balance FROM users WHERE id=?", (u["id"],)).fetchone()[0]
    audit(u["id"], "TOPUP", "wallet", u["id"], str(x.amount))
    return {"balance": bal}


@router.get("/coupons")
def coupons(u=Depends(current)):
    return rows("SELECT code,title,scope,kind,value,max_discount,min_amount FROM coupons WHERE active=1 AND (expires_at IS NULL OR expires_at>strftime('%s','now')) ORDER BY code")


@router.post("/coupons/validate")
def validate(x: CouponIn, u=Depends(current)):
    with tx() as c:
        try:
            disc, code = trips.evaluate_coupon(c, u["id"], x.code, x.amount, x.scope)
        except ApiError as e:
            return {"valid": False, "message": e.detail, "discount": 0, "final": x.amount}
    return {"valid": True, "code": code, "discount": disc, "final": round(x.amount - disc, 2), "message": f"{code} applied: you save Rs {disc:.0f}"}
