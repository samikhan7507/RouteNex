"""Atomic PostgreSQL rate limit shared by all API workers."""
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.models import utcnow


def consume(db: Session, key: str, limit: int, seconds: int, commit: bool = False):
    now = utcnow()
    count = db.scalar(text("""
        INSERT INTO rate_limits(key, window_start, count) VALUES (:key, :now, 1)
        ON CONFLICT (key) DO UPDATE SET
          count = CASE WHEN rate_limits.window_start <= :cutoff THEN 1 ELSE rate_limits.count + 1 END,
          window_start = CASE WHEN rate_limits.window_start <= :cutoff THEN :now ELSE rate_limits.window_start END
        RETURNING count
    """), {"key": key[:250], "now": now, "cutoff": now - timedelta(seconds=seconds)})
    # Commit successful limits too, so a later HTTP error cannot reset an attacker's counter.
    if commit:
        db.commit()
    if count > limit:
        raise HTTPException(429, "Too many attempts. Please wait a few minutes and try again", headers={"Retry-After": str(seconds)})


def clear(db: Session, key: str):
    db.execute(text("DELETE FROM rate_limits WHERE key=:key"), {"key": key})
