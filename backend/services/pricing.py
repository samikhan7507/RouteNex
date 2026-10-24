"""Fares, ETAs and surge - always computed on the server. Browser distance/duration are *hints* only."""
from datetime import datetime, timezone, timedelta
from services.geo import haversine_km

IST = timezone(timedelta(hours=5, minutes=30))
ROAD_FACTOR, MIN_RIDE_KM = 1.22, 0.1

RIDE_CLASSES = {
    "bike": {"label": "Bike", "seats": 1, "base": 20, "per_km": 7.0, "min_fare": 35, "speed": 30, "note": "Fastest in traffic"},
    "auto": {"label": "Auto", "seats": 3, "base": 30, "per_km": 10.0, "min_fare": 50, "speed": 24, "note": "Affordable for 3"},
    "cab": {"label": "Cab", "seats": 4, "base": 45, "per_km": 13.0, "min_fare": 80, "speed": 26, "note": "AC and comfortable"},
}
PARCEL_CLASSES = {
    "pbike": {"label": "Bike courier", "max_kg": 10, "base": 30, "per_km": 8.0, "min_fare": 49, "speed": 30, "note": "Up to 10 kg"},
    "pmini": {"label": "Mini cargo", "max_kg": 150, "base": 90, "per_km": 14.0, "min_fare": 149, "speed": 24, "note": "Up to 150 kg"},
    "pvan": {"label": "Van", "max_kg": 900, "base": 180, "per_km": 22.0, "min_fare": 299, "speed": 22, "note": "Up to 900 kg"},
}
SIZE_MULT = {"small": 1.0, "medium": 1.1, "large": 1.25}


def is_peak(now=None) -> bool:
    return 8 <= (now or datetime.now(IST)).hour <= 20


def traffic_factor(now=None) -> float:
    return 1.25 if is_peak(now) else 1.0


def demand_factor(waiting: int, free: int) -> float:
    """More waiting requests than free drivers -> higher multiplier (1.0 .. 1.5)."""
    ratio = (waiting + 1) / (free + 1)
    return round(min(1.5, 1.0 + 0.25 * max(0.0, ratio - 0.5)), 2)


def surge(demand: float, now=None) -> float:
    return round(min(1.8, demand * (1.1 if is_peak(now) else 1.0)), 2)


def resolve_distance(plat, plng, dlat, dlng, client_km=None, client_min=None) -> dict:
    straight = haversine_km(plat, plng, dlat, dlng)
    if straight < MIN_RIDE_KM:
        raise ValueError("Pickup and drop-off are too close")
    km = round(straight * ROAD_FACTOR, 2)
    if client_km is not None and straight * 0.95 <= client_km <= straight * 2.5 + 1:
        km = round(client_km, 2)          # a road route can't be shorter than the straight line
    return {"distance_km": km, "straight_km": round(straight, 2)}


def eta_minutes(km: float, speed_kmh: float, tf: float) -> int:
    return max(3, round(km / speed_kmh * 60 * tf))


def ride_quote(cls: str, km: float, sg: float, tf: float) -> dict:
    c = RIDE_CLASSES[cls]
    fare = max(c["min_fare"], round((c["base"] + km * c["per_km"]) * sg, 2))
    return {"vehicle_class": cls, "label": c["label"], "seats": c["seats"], "note": c["note"], "fare": fare,
            "eta_min": eta_minutes(km, c["speed"], tf), "surge": sg}


def feasible_parcel_classes(kg: float) -> list:
    return [k for k, c in PARCEL_CLASSES.items() if kg <= c["max_kg"]]


def parcel_quote(cls: str, km: float, kg: float, size: str, fragile: bool, sg: float, tf: float) -> dict:
    c = PARCEL_CLASSES[cls]
    weight_extra = {"pbike": max(0, kg - 3) * 5, "pmini": max(0, kg - 20) * 0.5, "pvan": max(0, kg - 150) * 0.2}[cls]
    core = (c["base"] + km * c["per_km"] + weight_extra) * SIZE_MULT[size] * sg
    fare = max(c["min_fare"], round(core + (25 if fragile else 0), 2))
    return {"vehicle_class": cls, "label": c["label"], "note": c["note"], "fare": fare,
            "eta_min": eta_minutes(km, c["speed"], tf), "surge": sg}


def resolve_trip(plat, plng, dlat, dlng, client_km=None, client_min=None, now=None) -> dict:
    """Backward-compatible single quote (cab)."""
    d = resolve_distance(plat, plng, dlat, dlng, client_km, client_min)
    tf = traffic_factor(now)
    q = ride_quote("cab", d["distance_km"], surge(1.0, now), tf)
    return {"distance_km": d["distance_km"], "fare": q["fare"], "eta_min": q["eta_min"], "traffic_factor": tf}
