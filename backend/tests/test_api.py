import pytest

RIDE = {"pickup": "A", "pickup_lat": 26.9, "pickup_lng": 75.8, "dropoff": "B", "drop_lat": 26.82, "drop_lng": 75.81}


# ---------- auth & security ----------
def test_health_and_login(client, auth):
    assert client.get("/api/health").json()["status"] == "healthy"; auth("c1@test.in")

def test_google_demo_cannot_impersonate_admin(client):
    r = client.post("/api/auth/google", json={"demo": True, "email": "admin@test.in", "name": "x"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "customer" and r.json()["user"]["email"] == "google.demo@routenex.in"

def test_login_rate_limit(client):
    for _ in range(8):
        assert client.post("/api/auth/login", json={"email": "c1@test.in", "password": "bad"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": "c1@test.in", "password": "Demo@123"}).status_code == 429

def test_otp_flow_and_wrong_code_limit(client):
    assert client.post("/api/auth/otp/request", json={"phone": "8882846897"}).status_code == 200
    assert client.post("/api/auth/otp/verify", json={"phone": "8882846897", "code": "123456"}).status_code == 200
    client.post("/api/auth/otp/request", json={"phone": "8882846897"})
    for _ in range(5):
        assert client.post("/api/auth/otp/verify", json={"phone": "8882846897", "code": "000000"}).status_code == 401
    assert client.post("/api/auth/otp/verify", json={"phone": "8882846897", "code": "123456"}).status_code == 429

def test_rbac(client, auth):
    assert client.get("/api/admin/users", headers=auth("c1@test.in")).status_code == 403
    assert client.get("/api/admin/users", headers=auth("admin@test.in")).status_code == 200

# ---------- shop ----------
def order(client, h, items, addr=1, **extra):
    return client.post("/api/orders", headers=h, json={"address_id": addr, "priority": 2, "delivery_window": "18:00", "items": items, **extra})

def test_order_stock_merge_and_restock(client, auth, sql):
    h = auth("c1@test.in")
    r = order(client, h, [{"item_id": 1, "quantity": 3}, {"item_id": 1, "quantity": 4}]); assert r.status_code == 200 and r.json()["total"] == 700
    assert sql("SELECT stock FROM items WHERE id=1")[0][0] == 3
    assert order(client, h, [{"item_id": 1, "quantity": 4}]).status_code == 409
    assert client.patch(f"/api/orders/{r.json()['id']}/cancel", headers=h).status_code == 200
    assert sql("SELECT stock FROM items WHERE id=1")[0][0] == 10

def test_customer_cannot_use_others_address_or_cancel_others_order(client, auth):
    h1, h2 = auth("c1@test.in"), auth("c2@test.in")
    assert order(client, h1, [{"item_id": 1, "quantity": 1}], addr=2).status_code == 404
    oid = order(client, h1, [{"item_id": 1, "quantity": 1}]).json()["id"]
    assert client.patch(f"/api/orders/{oid}/cancel", headers=h2).status_code == 404

def test_bad_cart_gives_readable_422(client, auth):
    r = order(client, auth("c1@test.in"), [{"item_id": 1, "quantity": 0}]); assert r.status_code == 422 and isinstance(r.json()["detail"], str)

# ---------- rides ----------
def test_ride_fare_cannot_be_tampered(client, auth):
    h = auth("c1@test.in")
    honest = client.post("/api/rides/estimate", headers=h, json=RIDE).json()
    cheat = client.post("/api/rides/estimate", headers=h, json={**RIDE, "route_distance_km": 0.01, "route_duration_min": 1}).json()
    assert honest["fare"] > 45 and cheat["fare"] == honest["fare"]

def test_ride_lifecycle_with_otp_and_ownership(client, auth, sql):
    h, d1, d2 = auth("c1@test.in"), auth("d1@test.in"), auth("d2@test.in")
    r = client.post("/api/rides", headers=h, json=RIDE).json(); rid = r["id"]
    assert r["status"] == "matched" and r["driver"]["id"] == 1 and "license" not in r["driver"] and r["otp"]
    assert client.post("/api/rides", headers=h, json=RIDE).status_code == 409                       # one active ride at a time
    assert client.post(f"/api/rides/{rid}/arrived", headers=d2).status_code == 403                  # not your trip
    assert client.patch(f"/api/rides/{rid}/status", headers=d1, json={"status": "completed"}).status_code == 403   # drivers can't skip OTP
    assert client.post(f"/api/rides/{rid}/start", headers=d1, json={"otp": r["otp"]}).status_code == 409           # must arrive first
    assert client.post(f"/api/rides/{rid}/arrived", headers=d1).status_code == 200
    wrong = "0000" if r["otp"] != "0000" else "1111"
    assert client.post(f"/api/rides/{rid}/start", headers=d1, json={"otp": wrong}).status_code == 401
    assert client.post(f"/api/rides/{rid}/start", headers=d1, json={"otp": r["otp"]}).status_code == 200
    assert client.post(f"/api/rides/{rid}/complete", headers=d1).status_code == 200
    assert tuple(sql("SELECT status,available FROM drivers WHERE id=1")[0]) == ("available", 1)
    assert sql("SELECT payment_status FROM rides WHERE id=?", (rid,))[0][0] == "paid"             # cash collected on completion

def test_no_double_booking_of_one_driver(client, auth):
    a = client.post("/api/rides", headers=auth("c1@test.in"), json=RIDE).json(); b = client.post("/api/rides", headers=auth("c2@test.in"), json=RIDE).json()
    assert a["status"] == "matched" and b["status"] == "searching"

# ---------- order lifecycle / optimizer ----------
def test_driver_scoping_and_status_flow_frees_resources(client, auth, sql):
    hc, d1, d2 = auth("c1@test.in"), auth("d1@test.in"), auth("d2@test.in")
    oid = order(client, hc, [{"item_id": 1, "quantity": 1}]).json()["id"]
    sql("INSERT INTO routes(vehicle_id,driver_id,status) VALUES(1,1,'planned')")
    sql("UPDATE orders SET route_id=1,status='assigned' WHERE id=?", (oid,)); sql("UPDATE drivers SET available=0,status='assigned' WHERE id=1")
    assert len(client.get("/api/orders", headers=d1).json()) == 1 and client.get("/api/orders", headers=d2).json() == []
    assert client.patch(f"/api/orders/{oid}/status", headers=d2, json={"status": "delivered"}).status_code == 403
    assert client.patch(f"/api/orders/{oid}/status", headers=d1, json={"status": "placed"}).status_code == 409
    for s in ("picked_up", "in_transit", "delivered"):
        assert client.patch(f"/api/orders/{oid}/status", headers=d1, json={"status": s}).status_code == 200
    assert sql("SELECT status FROM routes WHERE id=1")[0][0] == "completed" and sql("SELECT available FROM drivers WHERE id=1")[0][0] == 1

def test_optimizer_reroute_replans_automatically(client, auth):
    hc, hd = auth("c1@test.in"), auth("disp@test.in")
    order(client, hc, [{"item_id": 1, "quantity": 1}])
    r = client.post("/api/optimizer/run", headers=hd, json={}); assert r.status_code == 200 and r.json()["routes"][0]["vehicle"] == "V1"
    rr = client.post("/api/reroute", headers=hd, json={"event": "breakdown", "entity_type": "vehicle", "entity_id": 1, "message": "engine"}).json()
    assert rr["affected_routes"] and rr["reoptimized"]["routes"][0]["vehicle"] in ("V2", "V3") and rr["run_optimizer"] is False

def test_pricing_rejects_tiny_trip_and_optimizer_prefers_priority():
    from services.pricing import resolve_trip
    from services.optimizer import plan_routes
    with pytest.raises(ValueError): resolve_trip(26.9, 75.8, 26.9, 75.8)
    fleet = [{"id": 1, "capacity_kg": 100, "lat": 26.9, "lng": 75.8, "cost_per_km": 10, "plate": "X", "driver_id": 1}]
    orders = [{"id": 1, "lat": 26.95, "lng": 75.8, "priority": 1}, {"id": 2, "lat": 26.91, "lng": 75.8, "priority": 1}]
    plans, rest = plan_routes(orders, fleet); assert [o["id"] for o in plans[0]["orders"]] == [2, 1] and not rest
