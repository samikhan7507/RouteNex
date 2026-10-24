from typing import Optional
from fastapi import Header, HTTPException, Depends, Request
from db import one
from security import decode


def current(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Authentication required")
    try:
        data = decode(authorization[7:])
    except ValueError:
        raise HTTPException(401, "Invalid or expired token")
    u = one("SELECT id,name,email,phone,role,active FROM users WHERE id=?", (data.get("sub"),))
    if not u or not u["active"]:
        raise HTTPException(401, "Inactive account")
    return u


def roles(*allowed):
    def dep(u=Depends(current)):
        if u["role"] not in allowed:
            raise HTTPException(403, "Insufficient permission")
        return u
    return dep


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def driver_of(u):
    """The drivers-table profile for a user with role 'driver' (or None)."""
    return one("SELECT * FROM drivers WHERE user_id=?", (u["id"],))
