"""SYNTHETIC but realistic Jaipur data generators (there is no public per-trip dataset). The 'truth' functions below are the world the
models must learn; noise is added so the task is not trivial. In production, replace these with real trip / GPS logs (see load_real)."""
import math
import numpy as np
from ml import features as F


def weather_days(days, rng):
    """rain[d][h] in {0,1}: ~20% of days have a 2-6 hour rain spell."""
    rain = np.zeros((days, 24), dtype=int)
    for d in range(days):
        if rng.random() < 0.2:
            start, length = int(rng.integers(6, 20)), int(rng.integers(2, 7))
            rain[d, start:start + length] = 1
    return rain


def true_eta(vclass, km, hour, dow, rain, zone, load_kg, rng):
    cong = F.congestion(hour, dow, zone, rain)
    eff = F.FREE_KMH[vclass] * max(0.25, 1 - F.CONG_SENS[vclass] * cong)
    minutes = km / eff * 60 + 1.2 + 0.35 * km                              # stops, signals, parking
    if rain:
        minutes *= 1.08
    minutes += 0.004 * load_kg                                           # heavy loads are slower to handle
    return max(2.0, minutes * rng.lognormal(0, 0.17) + rng.normal(0, 1.8))


def make_eta(n, days=60, seed=7):
    rng = np.random.default_rng(seed)
    rain = weather_days(days, rng)
    hours_p = np.array([F.demand_curve(h) for h in range(24)]); hours_p /= hours_p.sum()
    X, y, day = [], [], []
    for _ in range(n):
        d = int(rng.integers(0, days)); h = int(rng.choice(24, p=hours_p)); dow = d % 7
        vc = F.VCLASSES[int(rng.choice(len(F.VCLASSES), p=[.22, .16, .20, .16, .10, .08, .08]))]
        zi = int(rng.integers(0, len(F.ZONES))); km = float(np.clip(rng.lognormal(1.55, 0.6), 0.6, 40))
        load = float(rng.choice([0, 0, 0, 2, 5, 20, 80, 300])) if vc.startswith("p") or vc == "truck" else 0.0
        r = int(rain[d, h])
        X.append(F.eta_row(vc, km, h, dow, r, zi, load)); y.append(true_eta(vc, km, h, dow, r, zi, load, rng)); day.append(d)
    return np.array(X, dtype=float), np.array(y), np.array(day)


def make_delay(n, days=60, seed=11):
    """One row per delivery stop. Label = the customer's delivery window was missed."""
    rng = np.random.default_rng(seed)
    rain = weather_days(days, rng)
    X, y, day = [], [], []
    for _ in range(n):
        d = int(rng.integers(0, days)); h = int(rng.integers(8, 21)); dow = d % 7; r = int(rain[d, h])
        vc = F.VCLASSES[int(rng.choice([0, 3, 4, 5, 6], p=[.15, .3, .25, .2, .1]))]
        zi = int(rng.integers(0, len(F.ZONES))); n_stops = int(rng.integers(2, 14)); seq = int(rng.integers(1, n_stops + 1))
        leg = float(np.clip(rng.lognormal(0.9, 0.6), 0.3, 25)); route_km = float(leg * seq * rng.uniform(0.7, 1.3) + rng.uniform(0, 5))
        load_ratio = float(rng.uniform(0.1, 1.0)); prio = int(rng.integers(1, 6)); cong = F.congestion(h, dow, zi, r)
        slack = float(rng.choice([rng.uniform(-8, 10), rng.uniform(5, 40), rng.uniform(20, 90)], p=[.3, .4, .3]))
        # actual delay accumulates leg by leg: traffic, rain, heavy loads, plus random incidents; later stops inherit earlier delays
        per_leg = cong * 2.2 + (1.8 if r else 0) + 0.35 * leg * (1 + cong) + 2.5 * load_ratio * (1.2 if vc in ("pvan", "truck") else 1) - 2.0
        delay = float(np.sum(rng.normal(per_leg, 4.5 + 0.3 * leg, size=seq))) + rng.normal(0, 6)   # + things we cannot observe
        if rng.random() < 0.12:
            delay += rng.exponential(15)                                  # breakdown / customer not home
        X.append([slack, seq, n_stops, leg, route_km, load_ratio, h, dow, r, cong, prio, F.vclass_code(vc)]); y.append(int(delay > slack)); day.append(d)
    return np.array(X, dtype=float), np.array(y), np.array(day)


def make_demand(days=70, seed=21):
    """Hourly requests (rides + parcels + orders) per area. Returns rows [zone,hour,dow,rain], counts, day index."""
    rng = np.random.default_rng(seed)
    rain = weather_days(days, rng)
    X, y, day = [], [], []
    for d in range(days):
        dow = d % 7; trend = 1 + 0.002 * d
        for h in range(24):
            for zi, z in enumerate(F.ZONES):
                lam = 14 * z[3] * F.demand_curve(h) * F.demand_dow_mult(dow) * (1 + 0.25 * rain[d, h]) * trend
                X.append([zi, h, dow, int(rain[d, h])]); y.append(int(rng.poisson(lam))); day.append(d)
    return np.array(X, dtype=float), np.array(y, dtype=float), np.array(day)


def load_real():
    """Hook for real data (completed trips with GPS timestamps). Returns None until you have it."""
    return None
