from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from app.core.ratelimit import consume
from app.core.security import current_user
from app.db import get_db
from app.models import User
from app.services import places

router = APIRouter(prefix="/api/places", tags=["locations"])


@router.get("/search")
def search(request: Request, q: str = Query(min_length=2, max_length=120), user: User = Depends(current_user), db: Session = Depends(get_db)):
    consume(db, f"places:{user.id}", 60, 60, commit=True)
    return places.search(db, q)
