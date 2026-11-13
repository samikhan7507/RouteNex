from __future__ import annotations
import logging
import secrets
from datetime import timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.ratelimit import clear, consume
from app.core.security import (create_session, current_session, current_user, hash_password, hash_secret,
                               login_event, otp_hash, public_user, verify_password)
from app.db import get_db
from app.models import OtpCode, User, UserSession, utcnow
from app.schemas import GoogleInput, Login, OtpVerify, PasswordInput, PhoneInput, ProfileInput, Register
from app.services.common import audit

router = APIRouter(prefix="/api/auth", tags=["authentication"])
log = logging.getLogger("routenex.auth")
DEMO_PHONE = "+919876543210"


@router.get("/config")
def config():
    s = get_settings()
    return {"demo_mode": s.demo_mode, "payment_provider": s.payment_provider, "location_provider": s.location_provider,
            "google_enabled": bool(s.google_client_id), "otp_provider": s.otp_provider,
            "demo_phone": DEMO_PHONE if s.demo_mode else None, "app_env": s.app_env}


@router.post("/register", status_code=201)
def register(body: Register, request: Request, response: Response, db: Session = Depends(get_db)):
    consume(db, f"register:{request.client.host}", 5, 3600, commit=True)
    if len(body.password) < 12:
        raise HTTPException(422, "Use a password of at least 12 characters")
    if db.scalar(select(User.id).where(User.email == body.email)):
        raise HTTPException(409, "An account with this email already exists. Sign in instead")
    user = User(name=body.name, email=body.email, password_hash=hash_password(body.password), role="customer")
    db.add(user)
    db.flush()
    audit(db, user, "REGISTER", "user", user.id)
    return create_session(db, user, request, response)


@router.post("/login")
def login(body: Login, request: Request, response: Response, db: Session = Depends(get_db)):
    key = f"login:{request.client.host}:{body.email}"
    consume(db, key, 8, 300, commit=True)
    user = db.scalar(select(User).where(User.email == body.email))
    valid = verify_password(body.password, user.password_hash if user else None)
    if not user or not valid or not user.active:
        login_event(db, request, body.email, user, False, "invalid_credentials_or_inactive")
        db.commit()
        raise HTTPException(401, "Email or password is incorrect")
    if user.password_hash and (not user.password_hash.startswith("$argon2") or PasswordHasherNeedsRehash(user.password_hash)):
        user.password_hash = hash_password(body.password)
    clear(db, key)
    return create_session(db, user, request, response)


def PasswordHasherNeedsRehash(encoded: str) -> bool:
    from argon2 import PasswordHasher
    try:
        return PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2).check_needs_rehash(encoded)
    except Exception:
        return False


@router.post("/otp/request")
def request_otp(body: PhoneInput, request: Request, db: Session = Depends(get_db)):
    s = get_settings()
    consume(db, f"otp-request:{request.client.host}:{body.phone}", 5, 300, commit=True)
    demo = s.demo_mode and body.phone == DEMO_PHONE
    code = "123456" if demo else f"{secrets.randbelow(1_000_000):06d}"
    for previous in db.scalars(select(OtpCode).where(OtpCode.phone == body.phone, OtpCode.consumed.is_(False)).with_for_update()):
        previous.consumed = True
    db.add(OtpCode(phone=body.phone, code_hash=otp_hash(body.phone, code), expires_at=utcnow() + timedelta(minutes=5)))
    if not demo:
        if s.otp_provider == "twilio":
            try:
                r = httpx.post(f"https://api.twilio.com/2010-04-01/Accounts/{s.twilio_account_sid}/Messages.json",
                               auth=(s.twilio_account_sid, s.twilio_auth_token),
                               data={"To": body.phone, "From": s.twilio_from_number, "Body": f"Your RouteNex verification code is {code}. It expires in 5 minutes. Do not share it."}, timeout=8)
                r.raise_for_status()
            except httpx.HTTPError:
                raise HTTPException(503, "SMS delivery is temporarily unavailable. Please try again shortly")
        else:
            log.warning("Development OTP for %s: %s (console provider; never enabled in production)", body.phone, code)
    db.commit()
    return {"message": "Verification code sent", "expires_in": 300, "demo": demo, "demo_code": code if demo else None}


@router.post("/otp/verify")
def verify_otp(body: OtpVerify, request: Request, response: Response, db: Session = Depends(get_db)):
    consume(db, f"otp-verify:{body.phone}", 8, 300, commit=True)
    row = db.scalar(select(OtpCode).where(OtpCode.phone == body.phone, OtpCode.consumed.is_(False)).order_by(OtpCode.id.desc()).with_for_update())
    import hmac
    if not row or row.expires_at <= utcnow() or row.attempts >= 5 or not hmac.compare_digest(row.code_hash, otp_hash(body.phone, body.code)):
        if row:
            row.attempts += 1
        login_event(db, request, body.phone, None, False, "invalid_otp", "otp")
        db.commit()
        raise HTTPException(401, "Verification code is incorrect or expired")
    row.consumed = True
    user = db.scalar(select(User).where(User.phone == body.phone).with_for_update())
    if not user:
        user = User(name="RouteNex customer", phone=body.phone, role="customer")
        db.add(user)
        db.flush()
    if not user.active:
        raise HTTPException(403, "This account is not active")
    return create_session(db, user, request, response, method="otp")


@router.post("/google")
def google(body: GoogleInput, request: Request, response: Response, db: Session = Depends(get_db)):
    s = get_settings()
    if not s.google_client_id:
        raise HTTPException(503, "Google sign-in is not configured")
    consume(db, f"google:{request.client.host}", 10, 300, commit=True)
    try:
        r = httpx.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": body.credential}, timeout=6)
        r.raise_for_status()
        claims = r.json()
    except httpx.HTTPError:
        raise HTTPException(503, "Google sign-in is temporarily unavailable")
    import time
    if claims.get("aud") != s.google_client_id or claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com") or str(claims.get("email_verified")).lower() != "true" or float(claims.get("exp", 0)) < time.time():
        raise HTTPException(401, "Google token could not be verified")
    email = claims["email"].lower()
    user = db.scalar(select(User).where(User.email == email).with_for_update())
    if user and user.role != "customer":
        raise HTTPException(403, "Staff accounts must sign in with their password")
    if not user:
        user = User(name=claims.get("name", "RouteNex customer")[:120], email=email, role="customer")
        db.add(user)
        db.flush()
    if not user.active:
        raise HTTPException(403, "This account is not active")
    return create_session(db, user, request, response, method="google")


@router.get("/me")
def me(request: Request, auth: tuple = Depends(current_session), db: Session = Depends(get_db)):
    user, session = auth
    import hmac
    supplied = request.headers.get("x-csrf-token", "")
    if supplied and hmac.compare_digest(hash_secret(supplied), session.csrf_hash):
        csrf = supplied
    else:
        csrf = secrets.token_urlsafe(32)
        session.csrf_hash = hash_secret(csrf)
    return {**public_user(user), "csrf_token": csrf, "session_expires_at": session.expires_at}


@router.patch("/me")
def update_profile(body: ProfileInput, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.name = body.name
    audit(db, user, "PROFILE_UPDATE", "user", user.id, request=request)
    return public_user(user)


@router.post("/change-password")
def change_password(body: PasswordInput, request: Request, response: Response, auth: tuple = Depends(current_session), db: Session = Depends(get_db)):
    user, session = auth
    consume(db, f"password:{user.id}", 5, 300, commit=True)
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    for other in db.scalars(select(UserSession).where(UserSession.user_id == user.id, UserSession.id != session.id, UserSession.revoked_at.is_(None))):
        other.revoked_at = utcnow()
    audit(db, user, "PASSWORD_CHANGE", "user", user.id, request=request)
    return {"message": "Password changed. Other devices were signed out"}


@router.post("/logout")
def logout(response: Response, auth: tuple = Depends(current_session), db: Session = Depends(get_db)):
    user, session = auth
    session.revoked_at = utcnow()
    response.delete_cookie(get_settings().cookie_name, path="/")
    audit(db, user, "LOGOUT", "user", user.id)
    return {"message": "Signed out"}


@router.get("/sessions")
def my_sessions(auth: tuple = Depends(current_session), db: Session = Depends(get_db)):
    user, current = auth
    rows = db.scalars(select(UserSession).where(UserSession.user_id == user.id, UserSession.revoked_at.is_(None), UserSession.expires_at > utcnow()).order_by(UserSession.created_at.desc()))
    return [{"id": s.id, "ip_address": s.ip_address, "user_agent": s.user_agent, "created_at": s.created_at,
             "last_seen_at": s.last_seen_at, "expires_at": s.expires_at, "current": s.id == current.id} for s in rows]


@router.delete("/sessions/{session_id}")
def revoke_own(session_id: str, auth: tuple = Depends(current_session), db: Session = Depends(get_db)):
    user, _ = auth
    row = db.scalar(select(UserSession).where(UserSession.id == session_id, UserSession.user_id == user.id).with_for_update())
    if not row:
        raise HTTPException(404, "Session not found")
    row.revoked_at = utcnow()
    return {"revoked": True}
