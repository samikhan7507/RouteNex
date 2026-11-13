"""Server-authoritative fares and short-lived, user-bound quote tokens (integer paise)."""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from app.core.config import get_settings
from app.services.geo import haversine_km

IST = timezone(timedelta(hours=5, minutes=30))
CLASSES = {
    "bike": {"label": "Bike", "kind": "ride", "seats": 1, "base": 2000, "per_km": 700, "minimum": 3500, "speed": 30, "note": "One passenger · helmet required"},
    "auto": {"label": "Auto", "kind": "ride", "seats": 3, "base": 3000, "per_km": 1000, "minimum": 5000, "speed": 24, "note": "Up to 3 passengers"},
    "cab": {"label": "Cab", "kind": "ride", "seats": 4, "base": 4500, "per_km": 1300, "minimum": 8000, "speed": 26, "note": "Up to 4 passengers · air conditioned"},
    "pbike": {"label": "Bike courier", "kind": "parcel", "max_kg": 10, "base": 3000, "per_km": 800, "minimum": 4900, "speed": 30, "note": "Documents and parcels up to 10 kg"},
    "pmini": {"label": "Mini cargo", "kind": "parcel", "max_kg": 150, "base": 9000, "per_km": 1400, "minimum": 14900, "speed": 24, "note": "Up to 150 kg"},
    "pvan": {"label": "Cargo van", "kind": "parcel", "max_kg": 900, "base": 18000, "per_km": 2200, "minimum": 29900, "speed": 22, "note": "Up to 900 kg"},
}


def _sign(payload: bytes) -> str:
    return hmac.new(get_settings().secret_key.encode(), payload, hashlib.sha256).hexdigest()


def issue_quote(user_id: int, data: dict) -> str:
    body = dict(data, user_id=user_id, expires_at=int(time.time()) + 300)
    payload = base64.urlsafe_b64encode(json.dumps(body, separators=(",", ":")).encode()).rstrip(b"=")
    return payload.decode() + "." + _sign(payload)


def read_quote(token: str, user_id: int) -> dict:
    try:
        raw, signature = token.split(".")
        if not hmac.compare_digest(_sign(raw.encode()), signature):
            raise ValueError
        data = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if data["user_id"] != user_id or data["expires_at"] < time.time():
            raise ValueError
        return data
    except Exception:
        raise HTTPException(409, "This fare quote has expired or changed. Request a fresh quote")


def quote_all(payload: dict, road: dict, waiting: int = 0, free: int = 1) -> dict:
    straight = haversine_km(payload.pickup.lat, payload.pickup.lng, payload.drop.lat, payload.drop.lng)
    if straight < 0.15:
        raise HTTPException(422, "Pickup and drop-off must be at least 150 metres apart")
    if straight > 150:
        raise HTTPException(422, "This pilot serves trips within 150 km of the pickup. Contact operations for longer trips")
    km = road["distance_km"]
    if not straight * 0.95 <= km <= straight * 3 + 2:
        raise HTTPException(502, "Road provider returned an inconsistent distance; please retry")
    now = datetime.now(IST)
    peak = 1.1 if 8 <= now.hour <= 20 else 1.0
    surge = round(min(1.5, peak * (1 + 0.15 * max(0, (waiting + 1) / (free + 1) - 0.5))), 2)
    quotes = []
    for key, c in CLASSES.items():
        if c["kind"] != payload.kind or (payload.kind == "parcel" and payload.weight_kg > c["max_kg"]):
            continue
        extra = 0
        if payload.kind == "parcel":
            size_factor = {"small": 1, "medium": 1.1, "large": 1.25}[payload.parcel_size]
            threshold = {"pbike": 3, "pmini": 20, "pvan": 150}[key]
            rate = {"pbike": 500, "pmini": 50, "pvan": 20}[key]
            extra = int(max(0, payload.weight_kg - threshold) * rate) + (2500 if payload.fragile else 0)
            core = int((c["base"] + km * c["per_km"] + extra) * size_factor * surge)
        else:
            core = int((c["base"] + km * c["per_km"]) * surge)
        eta = max(3, round(road.get("duration_min") or km / c["speed"] * 60 * (1.2 if peak > 1 else 1)))
        quotes.append({"vehicle_class": key, "label": c["label"], "note": c["note"], "seats": c.get("seats"),
                       "max_kg": c.get("max_kg"), "fare_paise": max(c["minimum"], core), "fare": max(c["minimum"], core) / 100,
                       "eta_min": eta, "surge": surge})
    data = {"kind": payload.kind, "pickup": payload.pickup.model_dump(), "drop": payload.drop.model_dump(),
            "weight_kg": payload.weight_kg if payload.kind == "parcel" else None,
            "parcel_size": payload.parcel_size, "fragile": payload.fragile, "distance_km": round(km, 2),
            "distance_source": road["source"], "quotes": quotes, "geometry": road.get("geometry", [])}
    return data


def delivery_fee(subtotal_paise: int) -> int:
    return 0 if subtotal_paise >= 49900 else 3900
