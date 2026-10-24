"""Phase 3 route optimizer: capacitated VRP with soft time windows and priorities.

Objective (minimised, in rupees):
    sum(distance x vehicle cost/km) + fixed cost per vehicle used + lateness penalty (per minute, priority-weighted)
    + penalty for every order left unassigned.
Method: priority-ordered cheapest insertion -> local search (2-opt, relocate, swap) until no improvement or time limit.
Pure Python, no dependencies, deterministic for a given seed. `baseline()` reproduces the old nearest-neighbour planner on the
same distance matrix so every result can show "before vs after".
"""
import random, time

SPEED_KMH = {"Bike": 28, "Electric Cargo": 24, "Mini Van": 26, "Van": 26, "Pickup": 26, "Reefer Van": 24, "Truck": 22, "EV Van": 26, "Tow Vehicle": 20, "Auto": 22, "Cab": 25}
LATE_RS_PER_MIN, FIXED_COST, UNASSIGNED_BASE, UNASSIGNED_PER_PRIORITY = 3.0, 40.0, 1500.0, 250.0
EPS = 1e-6


def peak_factor(t):
    return 1.25 if 8 * 60 <= t % 1440 <= 20 * 60 else 1.0


class Problem:
    def __init__(self, orders, vehicles, D, start_min, traffic=1.0, shift_end=22 * 60):
        """orders: dicts {id, weight, priority, win:(early,late), svc}. vehicles: dicts {id, cap, cpk, speed}.
        D: km matrix over points [vehicle depots..., orders...]."""
        self.ord, self.veh, self.D, self.V, self.N = orders, vehicles, D, len(vehicles), len(orders)
        self.start, self.traffic = start_min, traffic
        self.shift_end = max(shift_end, start_min + 180)
        for o in self.ord:
            o["late_w"] = 1.0 + 0.3 * (o["priority"] - 1)
        self._memo = {}

    def unassigned_cost(self, j):
        return UNASSIGNED_BASE + UNASSIGNED_PER_PRIORITY * self.ord[j]["priority"]

    def run(self, k, seq, hard=True):
        """Simulate vehicle k driving `seq` (order indices). -> dict or None if infeasible (capacity / end of shift)."""
        key = (k, tuple(seq), hard)
        if key in self._memo:
            return self._memo[key]
        v, t, pos, dist, late, load, arr = self.veh[k], float(self.start), k, 0.0, 0.0, 0.0, []
        res = None
        ok = True
        for j in seq:
            o = self.ord[j]
            load += o["weight"]
            if hard and load > v["cap"] + 1e-9:
                ok = False
                break
            d = self.D[pos][self.V + j]
            dist += d
            t += d / v["speed"] * 60.0 * peak_factor(t) * self.traffic
            e, l = o["win"]
            wait = max(0.0, e - t)
            t += wait
            lm = max(0.0, t - l)
            late += lm * o["late_w"]
            arr.append((round(t), round(wait), round(lm)))
            t += o["svc"]
            pos = self.V + j
        if ok and not (hard and seq and t > self.shift_end):
            res = {"cost": (dist * v["cpk"] + FIXED_COST + late * LATE_RS_PER_MIN) if seq else 0.0, "dist": dist, "late": late,
                   "load": load, "end": t, "arr": arr, "dur": t - self.start}
        self._memo[key] = res
        return res

    # ---------- construction ----------
    def best_insert(self, j, routes, rc):
        best = None
        for k, seq in enumerate(routes):
            for p in range(len(seq) + 1):
                r = self.run(k, seq[:p] + [j] + seq[p:])
                if r is None:
                    continue
                delta = r["cost"] - rc[k]
                if best is None or delta < best[0] - EPS:
                    best = (delta, k, p)
        return best

    def why_unassigned(self, j):
        o = self.ord[j]
        if o["weight"] > max(v["cap"] for v in self.veh) + 1e-9:
            return f"Too heavy ({o['weight']:.0f} kg) for any available vehicle"
        return "No vehicle can fit it (capacity or end of shift)"

    def solve(self, time_limit=1.5, seed=7):
        rnd = random.Random(seed)
        deadline = time.time() + time_limit
        routes = [[] for _ in range(self.V)]
        rc = [0.0] * self.V
        queue = sorted(range(self.N), key=lambda j: (-self.ord[j]["priority"], self.ord[j]["win"][1]))
        left = []
        for j in queue:
            b = self.best_insert(j, routes, rc)
            if b is None:
                left.append(j)
                continue
            _, k, p = b
            routes[k].insert(p, j)
            rc[k] = self.run(k, routes[k])["cost"]
        self._improve(routes, rc, left, deadline, rnd)
        reasons = {j: self.why_unassigned(j) for j in left}
        return routes, left, reasons

    # ---------- local search ----------
    def _improve(self, routes, rc, left, deadline, rnd):
        def refresh(k):
            rc[k] = self.run(k, routes[k])["cost"] if routes[k] else 0.0

        improved = True
        while improved and time.time() < deadline:
            improved = False
            for k in range(self.V):                                  # 2-opt inside a route
                seq = routes[k]
                for i in range(len(seq) - 1):
                    for j in range(i + 1, len(seq)):
                        new = seq[:i] + seq[i:j + 1][::-1] + seq[j + 1:]
                        r = self.run(k, new)
                        if r and r["cost"] < rc[k] - EPS:
                            routes[k] = seq = new
                            rc[k] = r["cost"]
                            improved = True
            order = [(k, j) for k in range(self.V) for j in routes[k]]
            rnd.shuffle(order)
            for k, j in order:                                       # relocate one order anywhere
                if time.time() > deadline:
                    break
                if j not in routes[k]:
                    continue
                base_k = [x for x in routes[k] if x != j]
                rk = self.run(k, base_k) if base_k else {"cost": 0.0}
                if rk is None:
                    continue
                best = None
                for k2 in range(self.V):
                    seq2 = base_k if k2 == k else routes[k2]
                    for p in range(len(seq2) + 1):
                        r2 = self.run(k2, seq2[:p] + [j] + seq2[p:])
                        if r2 is None:
                            continue
                        delta = (r2["cost"] - rc[k]) if k2 == k else (rk["cost"] - rc[k]) + (r2["cost"] - rc[k2])
                        if delta < -EPS and (best is None or delta < best[0]):
                            best = (delta, k2, p)
                if best:
                    _, k2, p = best
                    routes[k] = base_k
                    routes[k2].insert(p, j)
                    refresh(k)
                    refresh(k2)
                    improved = True
            for k1 in range(self.V):                                 # swap two orders between routes
                for k2 in range(k1 + 1, self.V):
                    for a in range(len(routes[k1])):
                        for b in range(len(routes[k2])):
                            if time.time() > deadline:
                                break
                            s1, s2 = routes[k1][:], routes[k2][:]
                            s1[a], s2[b] = s2[b], s1[a]
                            r1, r2 = self.run(k1, s1), self.run(k2, s2)
                            if r1 and r2 and r1["cost"] + r2["cost"] < rc[k1] + rc[k2] - EPS:
                                routes[k1], routes[k2] = s1, s2
                                rc[k1], rc[k2] = r1["cost"], r2["cost"]
                                improved = True
            for j in list(left):                                     # retry orders that did not fit before
                b = self.best_insert(j, routes, rc)
                if b and b[0] < self.unassigned_cost(j):
                    routes[b[1]].insert(b[2], j)
                    refresh(b[1])
                    left.remove(j)
                    improved = True

    # ---------- baseline (what the old planner did) ----------
    def baseline(self):
        order = sorted(range(self.V), key=lambda k: self.veh[k]["cap"])
        remaining = sorted(range(self.N), key=lambda j: (-self.ord[j]["priority"], self.ord[j]["win"][1]))
        routes = [[] for _ in range(self.V)]
        for k in order:
            load, chosen = 0.0, []
            for j in list(remaining):
                if load + self.ord[j]["weight"] <= self.veh[k]["cap"] + 1e-9:
                    chosen.append(j)
                    load += self.ord[j]["weight"]
                    remaining.remove(j)
            pos, seq = k, []
            while chosen:
                nxt = min(chosen, key=lambda j: self.D[pos][self.V + j])
                seq.append(nxt)
                chosen.remove(nxt)
                pos = self.V + nxt
            routes[k] = seq
        return routes, remaining

    def metrics(self, routes, left):
        dist = cost = late = 0.0
        used = 0
        for k, seq in enumerate(routes):
            if not seq:
                continue
            r = self.run(k, seq, hard=False)
            used += 1
            dist += r["dist"]
            late += sum(a[2] for a in r["arr"])
            cost += r["cost"]
        pen = sum(self.unassigned_cost(j) for j in left)
        return {"distance_km": round(dist, 2), "travel_cost": round(cost, 2), "late_minutes": int(late), "vehicles_used": used,
                "unassigned": len(left), "objective": round(cost + pen, 2)}


def build_problem(orders, vehicles, D, start_min, traffic=1.0):
    """orders: [{id, weight, priority, win, svc}] ; vehicles: [{id, type, cap, cpk}] -> Problem."""
    vs = [dict(v, speed=SPEED_KMH.get(v.get("type"), 25)) for v in vehicles]
    return Problem([dict(o) for o in orders], vs, D, start_min, traffic)


def service_minutes(weight_kg):
    return round(4 + min(10.0, weight_kg / 50.0), 1)


def pct(before, after):
    return round(100.0 * (before - after) / before, 1) if before else 0.0
