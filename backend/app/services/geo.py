"""Geospatial calculations; all coordinates are WGS84 latitude/longitude."""
import math


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def matrix(points: list[tuple[float, float]], road_factor: float = 1.22) -> list[list[float]]:
    return [[round(haversine_km(a[0], a[1], b[0], b[1]) * road_factor, 4) for b in points] for a in points]
