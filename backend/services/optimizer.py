"""Phase-0 optimizer (pure function, no DB). Greedy nearest-neighbour with priority bias.
Phase 3 replaces this with an OR-Tools VRP (capacity + time windows + road matrix)."""
from services.geo import haversine_km

KG_PER_ORDER = 5  # placeholder until orders carry real weight (Phase 2)


def _path_km(start, stops):
    km, lat, lng = 0.0, start[0], start[1]
    for o in stops:
        km += haversine_km(lat, lng, o["lat"], o["lng"]); lat, lng = o["lat"], o["lng"]
    return km


def plan_routes(pending, fleet, traffic_factor=1.15):
    remaining, plans = list(pending), []
    for v in sorted(fleet, key=lambda x: x["capacity_kg"]):
        if not remaining:
            break
        cap = max(1, int(v["capacity_kg"] // KG_PER_ORDER))
        take, remaining = remaining[:cap], remaining[cap:]
        baseline = _path_km((v["lat"], v["lng"]), take)          # visiting stops in arrival order
        lat, lng, total, seq, etas = v["lat"], v["lng"], 0.0, [], []
        while take:
            nxt = min(take, key=lambda o: haversine_km(lat, lng, o["lat"], o["lng"]) - o["priority"] * 0.15)
            total += haversine_km(lat, lng, nxt["lat"], nxt["lng"])
            lat, lng = nxt["lat"], nxt["lng"]
            take.remove(nxt); seq.append(nxt)
            etas.append(round((total * 3.1 + len(seq) * 6) * traffic_factor))
        plans.append({
            "vehicle": v, "orders": seq, "etas": etas,
            "distance_km": round(total, 2), "duration_min": etas[-1],
            "cost": round(total * v["cost_per_km"], 2),
            "saved_km": round(max(0.0, baseline - total), 2),
            "geometry": [[v["lat"], v["lng"]]] + [[o["lat"], o["lng"]] for o in seq],
        })
    return plans, remaining
