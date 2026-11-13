"""Cached Jaipur weather; offline fallback is explicitly labelled, never presented as live."""
import time
import httpx
from app.core.config import get_settings

_cache = {"at": 0.0, "data": None}
URL = "https://api.open-meteo.com/v1/forecast"


def snapshot() -> dict:
    now = time.time()
    ttl = 900 if _cache["data"] and _cache["data"]["source"] == "open-meteo" else 120
    if _cache["data"] and now - _cache["at"] < ttl:
        return _cache["data"]
    fallback = {"rain": False, "precip_mm": 0.0, "temp_c": None, "hourly_rain": [0] * 24, "source": "unavailable"}
    if not get_settings().weather_enabled:
        return fallback
    try:
        r = httpx.get(URL, params={"latitude": 26.9124, "longitude": 75.7873, "current": "temperature_2m,precipitation",
                                   "hourly": "precipitation", "forecast_hours": 26, "timezone": "Asia/Kolkata"}, timeout=2.5)
        r.raise_for_status()
        raw = r.json()
        cur = raw["current"]
        hourly = raw.get("hourly", {}).get("precipitation", [])[:24]
        data = {"rain": (cur.get("precipitation") or 0) >= 0.2, "precip_mm": cur.get("precipitation") or 0,
                "temp_c": cur.get("temperature_2m"), "hourly_rain": [1 if (x or 0) >= 0.2 else 0 for x in hourly] or [0] * 24,
                "source": "open-meteo"}
    except Exception:
        data = fallback
    _cache.update(at=now, data=data)
    return data
