"""Road routing with bounded timeouts and an explicitly labelled offline estimate."""
import httpx
from app.core.config import get_settings
from app.services.geo import haversine_km


def route(pickup: tuple[float, float], drop: tuple[float, float]) -> dict:
    settings = get_settings()
    straight = haversine_km(*pickup, *drop)
    fallback = {"distance_km": round(max(0.1, straight * 1.22), 2), "duration_min": None,
                "source": "estimate", "geometry": [list(pickup), list(drop)]}
    if not settings.routing_url:
        return fallback
    coords = f"{pickup[1]:.6f},{pickup[0]:.6f};{drop[1]:.6f},{drop[0]:.6f}"
    try:
        response = httpx.get(f"{settings.routing_url.rstrip('/')}/route/v1/driving/{coords}",
                             params={"overview": "full", "geometries": "geojson"}, timeout=3.0)
        response.raise_for_status()
        data = response.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            return fallback
        r = data["routes"][0]
        km, seconds = float(r["distance"]) / 1000, float(r["duration"]) / 60
        if not 0 < km < 1000 or not 0 < seconds < 24 * 60:
            return fallback
        return {"distance_km": round(km, 2), "duration_min": round(seconds, 1), "source": "osrm",
                "geometry": [[lat, lng] for lng, lat in r["geometry"]["coordinates"]]}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return fallback
