def place(client, h, qty=1, window="Today 08:00-22:00", item=1):
    r = client.post("/api/orders", headers=h, json={"address_id": 1, "priority": 3, "delivery_window": window, "items": [{"item_id": item, "quantity": qty}]}); assert r.status_code == 200, r.text
    return r.json()["id"]


def test_order_weight_is_stored(client, auth, sql):
    sql("UPDATE items SET weight_kg=7 WHERE id=1")
    oid = place(client, auth("c1@test.in"), qty=3)
    assert sql("SELECT weight_kg FROM orders WHERE id=?", (oid,))[0][0] == 21


def test_preview_does_not_save_and_apply_does(client, auth, sql):
    hc, hd = auth("c1@test.in"), auth("disp@test.in"); place(client, hc); place(client, hc)
    pv = client.post("/api/optimizer/run", headers=hd, json={"apply": False}).json()
    assert pv["applied"] is False and pv["routes"] and "improvement" in pv["metrics"] and pv["distance_source"] == "estimate"
    assert sql("SELECT COUNT(*) FROM routes")[0][0] == 0 and sql("SELECT COUNT(*) FROM orders WHERE status='assigned'")[0][0] == 0
    ap = client.post("/api/optimizer/run", headers=hd, json={}).json()
    assert ap["applied"] is True and ap["routes"][0]["route_id"] and sql("SELECT COUNT(*) FROM orders WHERE status='assigned'")[0][0] == 2
    stop = ap["routes"][0]["stop_details"][0]; assert {"arrive", "window", "late_min", "weight_kg"} <= set(stop)
    assert sql("SELECT arrival_min FROM route_orders LIMIT 1")[0][0] == stop["arrive_min"]


def test_heavy_order_goes_to_big_vehicle_or_is_reported(client, auth, sql):
    sql("UPDATE items SET weight_kg=500 WHERE id=2"); sql("UPDATE vehicles SET lat=26.9,lng=75.8 WHERE id=2")   # bring the big van into town
    hc, hd = auth("c1@test.in"), auth("disp@test.in")
    oid = place(client, hc, item=2)                                                   # 500 kg: only V2 (900 kg) can carry it
    r = client.post("/api/optimizer/run", headers=hd, json={}).json()
    assert [x["vehicle"] for x in r["routes"]] == ["V2"] and r["routes"][0]["orders"] == [oid]
    sql("UPDATE items SET weight_kg=5000 WHERE id=2"); oid2 = place(client, hc, item=2)
    r2 = client.post("/api/optimizer/run", headers=hd, json={"apply": False}).json()
    assert oid2 in r2["unassigned"] and "Too heavy" in r2["unassigned_detail"][0]["reason"]


def test_future_window_is_planned_later(client, auth, monkeypatch):
    from datetime import datetime
    from routers import ops
    from services.pricing import IST
    monkeypatch.setattr(ops, "_now_ist", lambda: datetime(2026, 10, 19, 10, 0, tzinfo=IST))      # it is 10:00
    hc, hd = auth("c1@test.in"), auth("disp@test.in")
    late = place(client, hc, window="14:00-16:00")                                                  # opens in 4 hours
    r = client.post("/api/optimizer/run", headers=hd, json={"apply": False}).json()
    assert r["routes"] == [] and r["excluded"][0]["order_id"] == late and "planned later" in r["excluded"][0]["reason"]
    soon = place(client, hc, window="11:00-13:00")                                                  # opens in 1 hour
    r2 = client.post("/api/optimizer/run", headers=hd, json={"apply": False}).json()
    assert [o for x in r2["routes"] for o in x["orders"]] == [soon] and [e["order_id"] for e in r2["excluded"]] == [late]


def test_window_that_already_ended_is_served_as_soon_as_possible(client, auth, monkeypatch):
    from datetime import datetime
    from routers import ops
    from services.pricing import IST
    monkeypatch.setattr(ops, "_now_ist", lambda: datetime(2026, 10, 19, 15, 0, tzinfo=IST))      # it is 15:00
    oid = place(client, auth("c1@test.in"), window="09:00-11:00")                                   # ended hours ago
    r = client.post("/api/optimizer/run", headers=auth("disp@test.in"), json={"apply": False}).json()
    assert r["routes"][0]["orders"] == [oid] and r["excluded"] == []


def test_driver_sees_route_and_can_deliver(client, auth, sql):
    hc, hd, d1 = auth("c1@test.in"), auth("disp@test.in"), auth("d1@test.in")
    oid = place(client, hc, window="Today 08:00-22:00")
    client.post("/api/optimizer/run", headers=hd, json={"vehicle_ids": [1]})
    rt = client.get("/api/driver/route", headers=d1).json()["route"]
    assert rt["plate"] == "V1" and rt["stops"][0]["order_id"] == oid and rt["stops"][0]["customer"] == "Cust1"
    assert client.get("/api/driver/route", headers=auth("d2@test.in")).json()["route"] is None
    for s in ("picked_up", "in_transit", "delivered"):
        assert client.patch(f"/api/orders/{oid}/status", headers=d1, json={"status": s}).status_code == 200
    assert client.get("/api/driver/route", headers=d1).json()["route"] is None          # route auto-completes


def test_stale_trip_expires_and_unblocks_booking(client, auth, sql):
    h = auth("c1@test.in"); ride = {"pickup": "A", "pickup_lat": 26.9, "pickup_lng": 75.8, "dropoff": "B", "drop_lat": 26.82, "drop_lng": 75.81}
    r = client.post("/api/rides", headers=h, json=ride).json()
    sql("UPDATE rides SET sim=0,matched_at=matched_at-10000 WHERE id=?", (r["id"],))   # an abandoned trip from days ago
    assert client.get("/api/rides", headers=h).json()[0]["status"] == "cancelled"
    assert sql("SELECT status FROM drivers WHERE id=1")[0][0] == "available"
    assert client.post("/api/rides", headers=h, json=ride).status_code == 200


def test_optimizer_overview_counts_only_usable_fleet(client, auth, sql):
    hc, hd = auth("c1@test.in"), auth("disp@test.in"); place(client, hc)
    assert client.get("/api/optimizer/overview", headers=hd).json() == {"pending": 1, "vehicles": 3}
    sql("UPDATE drivers SET service='ride' WHERE id=1")                                # a ride-only driver is not usable for deliveries
    assert client.get("/api/optimizer/overview", headers=hd).json()["vehicles"] == 2
    assert client.get("/api/optimizer/overview", headers=hc).status_code == 403
