"""Password/OTP hashing and database-backed, revocable browser sessions."""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db
from app.models import LoginEvent, User, UserSession, utcnow

_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)
_DUMMY = _hasher.hash("not-a-real-account-password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        try:
            _hasher.verify(_DUMMY, password)
        except VerificationError:
            pass
        return False
    if not encoded.startswith("$argon2"):
        # Legacy v2 PBKDF2 hashes migrate transparently after a successful login.
        try:
            salt, expected = encoded.split("$", 1)
            actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 210000).hex()
            return hmac.compare_digest(actual, expected)
        except (ValueError, TypeError):
            return False
    try:
        return _hasher.verify(encoded, password)
    except (VerificationError, InvalidHashError):
        return False


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def otp_hash(phone: str, code: str) -> str:
    return hmac.new(get_settings().secret_key.encode(), f"otp:{phone}:{code}".encode(), hashlib.sha256).hexdigest()


def proof_code(reference: str, purpose: str = "pickup") -> str:
    """Reproducible ONLY inside the explicitly labelled simulator, never a real OTP."""
    settings = get_settings()
    if not settings.demo_mode:
        raise RuntimeError("Simulated proof codes are disabled")
    n = int(hash_secret(f"{settings.secret_key}:{purpose}:{reference}")[:12], 16)
    return f"{n % 1_000_000:06d}"


def public_user(user: User) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email, "phone": user.phone,
            "role": user.role, "active": user.active, "wallet_balance": user.wallet_balance_paise / 100,
            "created_at": user.created_at, "last_login_at": user.last_login_at}


def login_event(db: Session, request: Request, email: str, user: User | None, success: bool, reason: str = "", method: str = "password"):
    db.add(LoginEvent(email=email[:254], user_id=user.id if user else None, success=success,
                      reason=reason, method=method, ip_address=request.client.host if request.client else "",
                      user_agent=request.headers.get("user-agent", "")[:512]))


def create_session(db: Session, user: User, request: Request, response: Response, method: str = "password") -> dict:
    settings = get_settings()
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    now = utcnow()
    session = UserSession(user_id=user.id, token_hash=hash_secret(token), csrf_hash=hash_secret(csrf),
                          ip_address=request.client.host if request.client else "",
                          user_agent=request.headers.get("user-agent", "")[:512],
                          expires_at=now + timedelta(hours=settings.session_hours))
    user.last_login_at = now
    db.add(session)
    login_event(db, request, user.email or user.phone or "", user, True, method=method)
    db.flush()
    response.set_cookie(settings.cookie_name, token, max_age=settings.session_hours * 3600,
                        httponly=True, secure=settings.secure_cookies, samesite="lax", path="/")
    return {"user": public_user(user), "csrf_token": csrf, "expires_at": session.expires_at}


def current_session(request: Request, db: Session = Depends(get_db)) -> tuple[User, UserSession]:
    settings = get_settings()
    token = request.cookies.get(settings.cookie_name, "")
    # Bearer support is limited to explicit API clients; browsers use HttpOnly cookies.
    if not token and request.headers.get("authorization", "").startswith("Bearer "):
        token = request.headers["authorization"][7:]
    if not token:
        raise HTTPException(401, "Please sign in to continue")
    session = db.scalar(select(UserSession).where(UserSession.token_hash == hash_secret(token)))
    now = utcnow()
    if not session or session.revoked_at or session.expires_at <= now or session.last_seen_at + timedelta(minutes=settings.session_idle_minutes) <= now:
        raise HTTPException(401, "Your session has expired. Please sign in again")
    user = db.get(User, session.user_id)
    if not user or not user.active:
        raise HTTPException(401, "This account is not active")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        supplied = request.headers.get("x-csrf-token", "")
        if not supplied or not hmac.compare_digest(hash_secret(supplied), session.csrf_hash):
            raise HTTPException(403, "Security token missing or expired. Refresh and try again")
        origin = request.headers.get("origin")
        if origin and origin not in settings.origins and origin != settings.base_url.rstrip("/"):
            # Same-origin SPA calls must work on localhost, 127.0.0.1 and proxied previews
            # without a wildcard CORS allowlist. Trust the request Host, not arbitrary origins.
            parts = urlsplit(origin)
            host = request.headers.get("host", request.url.netloc)
            same_host = parts.netloc == host
            scheme_ok = parts.scheme == request.url.scheme or (
                not settings.is_production and parts.scheme == "https" and parts.hostname and parts.hostname.endswith(".e2b.app")
            )
            if not (same_host and scheme_ok and parts.scheme in {"http", "https"}):
                raise HTTPException(403, "Origin not allowed")
    if now - session.last_seen_at > timedelta(seconds=60):
        db.execute(update(UserSession).where(UserSession.id == session.id).values(last_seen_at=now))
    return user, session


def current_user(auth: tuple[User, UserSession] = Depends(current_session)) -> User:
    return auth[0]


def require_roles(*allowed: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(403, "You do not have permission to perform this action")
        return user
    return dependency


import base64
from cryptography.fernet import Fernet, InvalidToken


def _proof_cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256((get_settings().secret_key + ":proof-encryption").encode()).digest())
    return Fernet(key)


def protect_code(code: str) -> str:
    return _proof_cipher().encrypt(code.encode()).decode()


def reveal_code(encrypted: str | None) -> str | None:
    if not encrypted:
        return None
    try:
        return _proof_cipher().decrypt(encrypted.encode()).decode()
    except InvalidToken:
        return None
