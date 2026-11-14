import config
from fastapi import APIRouter, HTTPException, Depends, Request
from db import one, run, audit
from deps import current, client_ip
from schemas import Login, PhoneIn, OtpVerify, GoogleIn
from security import verify_password, token, otp_hash, new_otp, RateLimiter
import hmac, time

router = APIRouter(prefix="/api", tags=["auth"])
login_limiter = RateLimiter(8, 300)    # failed logins per IP+email
otp_req_limiter = RateLimiter(5, 300)  # OTP requests per IP+phone
otp_ver_limiter = RateLimiter(5, 300)  # failed OTP checks per phone

PUBLIC = ("id", "name", "email", "phone", "role")


def _session(u):
    return {"access_token": token({"sub": u["id"], "role": u["role"]}, config.TOKEN_MINUTES),
            "token_type": "bearer", "user": {k: u[k] for k in PUBLIC}}


@router.post("/auth/login")
def login(x: Login, request: Request):
    key = f"{client_ip(request)}:{x.email.lower()}"
    if login_limiter.is_blocked(key):
        raise HTTPException(429, "Too many failed attempts. Try again in a few minutes.")
    u = one("SELECT * FROM users WHERE email=?", (x.email.lower(),))
    if not u or not u["active"] or not verify_password(x.password, u["password_hash"] or ""):
        login_limiter.record(key)
        raise HTTPException(401, "Invalid credentials")
    login_limiter.clear(key)
    audit(u["id"], "LOGIN", "user", u["id"])
    return _session(u)


@router.post("/auth/otp/request")
def otp_request(x: PhoneIn, request: Request):
    key = f"{client_ip(request)}:{x.phone}"
    if otp_req_limiter.is_blocked(key):
        raise HTTPException(429, "Too many OTP requests. Please wait a few minutes.")
    otp_req_limiter.record(key)
    is_demo = config.DEMO_MODE and x.phone == config.DEMO_PHONE
    code = "123456" if is_demo else new_otp()
    run("UPDATE otp_codes SET consumed=1 WHERE phone=? AND consumed=0", (x.phone,))
    run("INSERT INTO otp_codes(phone,code_hash,expires_at) VALUES(?,?,?)", (x.phone, otp_hash(x.phone, code), int(time.time()) + 300))
    if config.OTP_PROVIDER == "console" and not is_demo:
        print(f"[OTP] {x.phone}: {code}  (console provider - dev only)")
    # TODO(prod): send via SMS provider adapter. The code is never returned in the response.
    return {"message": "OTP sent", "expires_in": 300, "demo": is_demo}


@router.post("/auth/otp/verify")
def otp_verify(x: OtpVerify):
    if otp_ver_limiter.is_blocked(x.phone):
        raise HTTPException(429, "Too many wrong codes. Request a new OTP in a few minutes.")
    r = one("SELECT * FROM otp_codes WHERE phone=? AND consumed=0 ORDER BY id DESC LIMIT 1", (x.phone,))
    ok = bool(r) and r["expires_at"] >= time.time() and hmac.compare_digest(r["code_hash"], otp_hash(x.phone, x.code))
    if not ok:
        otp_ver_limiter.record(x.phone)
        raise HTTPException(401, "Invalid or expired OTP")
    run("UPDATE otp_codes SET consumed=1 WHERE id=?", (r["id"],))
    otp_ver_limiter.clear(x.phone)
    u = one("SELECT * FROM users WHERE phone=?", (x.phone,))
    if not u:
        uid = run("INSERT INTO users(name,phone,role) VALUES(?,?,?)", ("Mobile User", x.phone, "customer"))
        u = one("SELECT * FROM users WHERE id=?", (uid,))
    if not u["active"]:
        raise HTTPException(401, "Inactive account")
    return _session(u)


@router.post("/auth/google")
def google(body: GoogleIn):
    # SECURITY FIX: the old version trusted a client-supplied email, so anyone could sign in as admin.
    # Demo mode now always maps to ONE fixed customer profile; real Google sign-in needs ID-token verification.
    if not config.DEMO_MODE:
        raise HTTPException(501, "Google sign-in is not configured (set GOOGLE_CLIENT_ID and add ID-token verification)")
    email = "google.demo@routenex.in"
    u = one("SELECT * FROM users WHERE email=?", (email,))
    if not u:
        uid = run("INSERT INTO users(name,email,role) VALUES(?,?,?)", ("Google Demo User", email, "customer"))
        u = one("SELECT * FROM users WHERE id=?", (uid,))
    return _session(u)


@router.get("/me")
def me(u=Depends(current)):
    return u
