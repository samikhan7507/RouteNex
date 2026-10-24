"""Road-distance matrix. Tries the public OSRM 'table' service; falls back to straight-line x detour factor when offline."""
import json, os, urllib.request
from services.geo import haversine_km

DETOUR = 1.3
_cache = {}


def matrix(points, use_roads=True, timeout=4.0):
    """points = [(lat, lng), ...] -> (km matrix, source) where source is 'osrm' or 'estimate'."""
    n = len(points)
    if use_roads and 2 <= n <= 80 and not os.getenv("ROUTENEX_OFFLINE"):
        key = tuple((round(p[0], 4), round(p[1], 4)) for p in points)
        if key in _cache:
            return _cache[key]
        try:
            coords = ";".join(f"{p[1]:.5f},{p[0]:.5f}" for p in points)
            url = f"https://router.project-osrm.org/table/v1/driving/{coords}?annotations=distance"
            with urllib.request.urlopen(url, timeout=timeout) as r:
                d = json.load(r)
            if d.get("code") == "Ok" and d.get("distances") and all(x is not None for row in d["distances"] for x in row):
                res = ([[x / 1000.0 for x in row] for row in d["distances"]], "osrm")
                if len(_cache) > 50:
                    _cache.clear()
                _cache[key] = res
                return res
        except Exception:
            pass
    est = [[0.0 if i == j else haversine_km(a[0], a[1], b[0], b[1]) * DETOUR for j, b in enumerate(points)] for i, a in enumerate(points)]
    return est, "estimate"
