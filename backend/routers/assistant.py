from typing import Optional
from fastapi import APIRouter, Depends
from deps import current
from schemas import ChatIn, ActionIn
from security import RateLimiter
from services import assistant, llm
from services.errors import ApiError
import config

router = APIRouter(prefix="/api/assistant", tags=["assistant"])
limiter = RateLimiter(config.ASSISTANT_PER_MIN, 60)


def _throttle(u):
    k = f"u{u['id']}"
    if limiter.is_blocked(k):
        raise ApiError(429, "You're sending messages very fast. Please wait a few seconds.")
    limiter.record(k)


@router.get("/status")
def status(u=Depends(current)):
    p = llm.get_provider()
    return {"provider": p.label if p else "offline", "remote": bool(p and p.remote), "suggestions": assistant.suggestions(u["role"]),
            "note": "Running on the built-in engine (no AI model detected)." if not p else ("Cloud model: phone numbers and emails are removed before sending." if p.remote else "Local model: nothing leaves this computer.")}


@router.post("/chat")
def chat(x: ChatIn, u=Depends(current)):
    _throttle(u)
    if not x.message.strip():
        raise ApiError(400, "Type a message first")
    return assistant.handle(u, x.message, x.history)


@router.post("/confirm")
def confirm(x: ActionIn, u=Depends(current)):
    _throttle(u)
    return assistant.confirm(u, x.id)


@router.post("/dismiss")
def dismiss(x: ActionIn, u=Depends(current)):
    return assistant.dismiss(u, x.id)
