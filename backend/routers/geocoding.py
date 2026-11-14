from fastapi import APIRouter, Depends, Query
from deps import current
from security import RateLimiter
from services import geocoding
from services.errors import ApiError

router = APIRouter(prefix='/api/places', tags=['places'])
limiter = RateLimiter(60, 60)


@router.get('/search')
def search(q: str = Query(min_length=3, max_length=120), user=Depends(current)):
    q = ' '.join(q.split())
    if len(q) < 3:
        raise ApiError(400, 'Enter at least 3 characters')
    key = str(user['id'])
    if limiter.is_blocked(key):
        raise ApiError(429, 'Too many searches. Please wait a moment.')
    limiter.record(key)
    return geocoding.search(q)
