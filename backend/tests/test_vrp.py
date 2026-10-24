import random
from services import vrp, roads, windows


def instance(n, seed=3, heavy=False):
    rnd = random.Random(seed)
    vehicles = [{"id": i, "type": t, "cap": c, "cpk": k, "lat": 26.9 + rnd.uniform(-.05, .05), "lng": 75.8 + rnd.uniform(-.05, .05)}
                for i, (t, c, k) in enumerate([("Bike", 20, 4), ("Bike", 25, 4.2), ("Van", 900, 14), ("Mini Van", 650, 12), ("Pickup", 1200, 17)])]
    orders = [{"id": 100 + i, "weight": rnd.choice([1, 2, 5, 8, 12, 40, 120] + ([300] if heavy else [])), "priority": rnd.randint(1, 5),
               "lat": 26.9 + rnd.uniform(-.08, .08), "lng": 75.8 + rnd.uniform(-.08, .08)} for i in range(n)]
    for o in orders:
        a = rnd.choice([13 * 60, 14 * 60, 15 * 60, 16 * 60]); o["win"] = (a, a + 120); o["svc"] = vrp.service_minutes(o["weight"])
    D, src = roads.matrix([(v["lat"], v["lng"]) for v in vehicles] + [(o["lat"], o["lng"]) for o in orders])
    assert src == "estimate"        # tests run offline (ROUTENEX_OFFLINE=1)
    return orders, vehicles, D


def test_parse_windows():
    assert windows.parse_window("09:00\u201311:00") == (540, 660) and windows.parse_window("Today 18:00\u201321:00") == (1080, 1260)
    assert windows.parse_window("9-11") == (540, 660) and windows.parse_window("18:00") == (480, 1320) and windows.clock(1085) == "18:05"


def test_solution_is_valid_and_never_worse_than_baseline():
    for n, heavy in ((8, False), (20, False), (35, True)):
        orders, vehicles, D = instance(n, heavy=heavy)
        P = vrp.build_problem(orders, vehicles, D, start_min=13 * 60)
        routes, left, reasons = P.solve(time_limit=1.0)
        flat = [j for r in routes for j in r]
        assert len(flat) == len(set(flat)) and len(flat) + len(left) == n          # each order planned at most once, none lost
        for k, seq in enumerate(routes):
            assert sum(orders[j]["weight"] for j in seq) <= vehicles[k]["cap"] + 1e-6   # capacity is a hard rule
            assert not seq or P.run(k, seq) is not None
        assert P.metrics(routes, left)["objective"] <= P.metrics(*P.baseline())["objective"] + 1e-6


def test_too_heavy_order_is_reported_not_forced():
    orders, vehicles, D = instance(6)
    orders[0]["weight"] = 5000
    P = vrp.build_problem(orders, vehicles, D, start_min=13 * 60)
    routes, left, reasons = P.solve(time_limit=0.5)
    assert 0 in left and "Too heavy" in reasons[0]


def test_priority_orders_are_served_first_when_capacity_is_tight():
    orders, vehicles, D = instance(10)
    vehicles = vehicles[:1]; vehicles[0]["cap"] = 12; D = [[0.0 if i == j else 3.0 for j in range(11)] for i in range(11)]
    for o in orders: o["weight"] = 6.0
    orders[3]["priority"] = orders[7]["priority"] = 5
    for i, o in enumerate(orders):
        if i not in (3, 7): o["priority"] = 1
    routes, left, _ = vrp.build_problem(orders, vehicles, D, 13 * 60).solve(time_limit=0.5)
    assert sorted(routes[0]) == [3, 7]                                            # only two fit; the two priority-5 orders win


def test_deterministic_for_same_seed():
    orders, vehicles, D = instance(20)
    a = vrp.build_problem(orders, vehicles, D, 13 * 60).solve(time_limit=1.0)[0]
    b = vrp.build_problem(orders, vehicles, D, 13 * 60).solve(time_limit=1.0)[0]
    assert a == b
