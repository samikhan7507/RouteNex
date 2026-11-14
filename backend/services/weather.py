"""Live Jaipur weather from Open-Meteo (free, no key). Cached; silently falls back to 'clear' when offline."""
import json, os, time, urllib.request

URL = ("https://api.open-meteo.com/v1/forecast?latitude=26.9124&longitude=75.7873&current=temperature_2m,precipitation"
       "&hourly=precipitation&forecast_hours=26&timezone=Asia%2FKolkata")
_cache = {"at": 0.0, "data": None}
TTL_OK, TTL_FAIL = 900, 300


def _fetch():
    if os.getenv("ROUTENEX_OFFLINE"):
        return None
    try:
        with urllib.request.urlopen(URL, timeout=2.5) as r:
            return json.load(r)
    except Exception:
        return None


def snapshot():
    """-> {'rain': bool, 'precip_mm': float, 'temp_c': float|None, 'hourly_rain': [0/1 x24], 'source': 'open-meteo'|'default'}"""
    now = time.time()
    ttl = TTL_OK if _cache["data"] and _cache["data"]["source"] == "open-meteo" else TTL_FAIL
    if _cache["data"] and now - _cache["at"] < ttl:
        return _cache["data"]
    raw = _fetch()
    if raw and raw.get("current"):
        cur = raw["current"]; hourly = (raw.get("hourly") or {}).get("precipitation") or []
        data = {"rain": (cur.get("precipitation") or 0) >= 0.2, "precip_mm": cur.get("precipitation") or 0.0, "temp_c": cur.get("temperature_2m"),
                "hourly_rain": [1 if (x or 0) >= 0.2 else 0 for x in hourly[:24]] or [0] * 24, "source": "open-meteo"}
    else:
        data = {"rain": False, "precip_mm": 0.0, "temp_c": None, "hourly_rain": [0] * 24, "source": "default"}
    _cache.update(at=now, data=data)
    return data
