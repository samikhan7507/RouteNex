"""Shared by training AND serving, so a feature can never be computed two different ways. Pure Python (no numpy/sklearn needed)."""
import math

# name, lat, lng, demand weight, congestion bias  (same 12 Jaipur areas as the demo data)
ZONES = [("C-Scheme", 26.9124, 75.7873, 1.30, 1.15), ("Malviya Nagar", 26.8540, 75.8243, 1.10, 1.00), ("Vaishali Nagar", 26.9126, 75.7442, 1.05, 0.95),
         ("Mansarovar", 26.8505, 75.7628, 1.00, 0.95), ("Jagatpura", 26.8399, 75.8322, 0.75, 0.85), ("Raja Park", 26.8942, 75.8210, 1.15, 1.20),
         ("Bani Park", 26.9322, 75.7933, 0.90, 1.00), ("Tonk Road", 26.8735, 75.7950, 1.10, 1.25), ("Amer", 26.9855, 75.8513, 0.50, 0.80),
         ("Sitapura", 26.7751, 75.8514, 0.55, 0.80), ("Jhotwara", 26.9540, 75.7420, 0.70, 0.90), ("Civil Lines", 26.9064, 75.7790, 0.95, 1.05)]
VCLASSES = ["bike", "auto", "cab", "pbike", "pmini", "pvan", "truck"]
FREE_KMH = {"bike": 30, "auto": 24, "cab": 26, "pbike": 30, "pmini": 24, "pvan": 22, "truck": 20}
CONG_SENS = {"bike": 0.7, "auto": 1.0, "cab": 1.0, "pbike": 0.7, "pmini": 1.0, "pvan": 1.1, "truck": 1.15}
VEHICLE_TYPE_TO_CLASS = {"Bike": "pbike", "Auto": "auto", "Cab": "cab", "Electric Cargo": "pmini", "Mini Van": "pmini", "EV Van": "pmini",
                         "Van": "pvan", "Pickup": "pvan", "Reefer Van": "pvan", "Truck": "truck", "Tow Vehicle": "truck"}
ETA_FEATURES = ["distance_km", "hour", "dow", "rain", "cong", "vclass", "load_kg"]
DELAY_FEATURES = ["slack", "seq", "n_stops", "leg_km", "route_km", "load_ratio", "hour", "dow", "rain", "cong", "priority", "vclass"]
DEMAND_FEATURES = ["zone", "hour", "dow", "rain"]


def vclass_code(name):
    return VCLASSES.index(name) if name in VCLASSES else VCLASSES.index("truck")


def zone_index(lat, lng):
    best, bd = 0, 1e9
    for i, z in enumerate(ZONES):
        d = (z[1] - lat) ** 2 + ((z[2] - lng) * math.cos(math.radians(26.9))) ** 2
        if d < bd:
            best, bd = i, d
    return best


def base_curve(h):
    return 0.45 * math.exp(-((h - 9.5) ** 2) / (2 * 1.3 ** 2)) + 0.55 * math.exp(-((h - 18.5) ** 2) / (2 * 1.6 ** 2)) + 0.12 * math.exp(-((h - 14) ** 2) / (2 * 3 ** 2))


def congestion(hour, dow, zone, rain):
    """Known traffic-pressure index 0..0.85 for an area at a time (a static profile the app can compute at serving time)."""
    c = base_curve(hour) * ZONES[zone][4] * (0.75 if dow >= 5 else 1.0) + (0.2 * (0.5 + base_curve(hour)) if rain else 0.0)
    return round(min(0.85, c), 4)


def demand_curve(h):
    return 0.05 + 0.5 * math.exp(-((h - 9) ** 2) / (2 * 1.5 ** 2)) + 0.6 * math.exp(-((h - 13) ** 2) / (2 * 1.4 ** 2)) + 1.0 * math.exp(-((h - 19) ** 2) / (2 * 1.8 ** 2))


def demand_dow_mult(dow):
    return {4: 1.1, 5: 1.2, 6: 1.15}.get(dow, 1.0)


def eta_row(vclass, km, hour, dow, rain, zone, load_kg=0.0):
    return [float(km), int(hour), int(dow), int(bool(rain)), congestion(hour, dow, zone, rain), vclass_code(vclass), float(load_kg)]


def heuristic_eta(vclass, km, hour):
    """What the app used before ML: free-flow speed x peak-hour factor."""
    return max(3, round(km / FREE_KMH.get(vclass, 25) * 60 * (1.25 if 8 <= hour <= 20 else 1.0)))
