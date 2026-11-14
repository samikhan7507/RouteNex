RIDE = {"pickup": "A", "pickup_lat": 26.9, "pickup_lng": 75.8, "dropoff": "B", "drop_lat": 26.82, "drop_lng": 75.81}
PARCEL = {**RIDE, "weight_kg": 4, "size": "small", "fragile": False, "description": "books", "recipient_name": "Ravi", "recipient_phone": "9876543210"}


def topup(client, h, n):
    return client.post("/api/wallet/topup", headers=h, json={"amount": n}).json()["balance"]

def balance(client, h):
    return client.get("/api/wallet", headers=h).json()["balance"]


def test_estimate_returns_three_classes_with_availability(client, auth):
    r = client.post("/api/rides/estimate", headers=auth("c1@test.in"), json=RIDE).json()
    assert [o["vehicle_class"] for o in r["options"]] == ["bike", "auto", "cab"]
    fares = [o["fare"] for o in r["options"]]; assert fares == sorted(fares)
    cab = r["options"][2]; assert cab["nearby"] >= 1 and cab["pickup_eta_min"] is not None and r["fare"] == cab["fare"]
    assert r["options"][1]["nearby"] == 0                                    # no Auto in the fixture

def test_wallet_payment_and_refund_on_cancel(client, auth):
    h = auth("c1@test.in"); assert topup(client, h, 500) == 500
    r = client.post("/api/rides", headers=h, json={**RIDE, "payment_method": "wallet"}).json()
    assert r["payment_status"] == "paid" and abs(balance(client, h) - (500 - r["payable"])) < 0.01
    c = client.post(f"/api/rides/{r['id']}/cancel", headers=h, json={}); assert c.status_code == 200 and c.json()["refund"] > 0
    assert abs(balance(client, h) - 500) < 0.01

def test_insufficient_wallet_blocks_booking_and_rolls_back(client, auth, sql):
    h = auth("c1@test.in")
    r = client.post("/api/rides", headers=h, json={**RIDE, "payment_method": "wallet"}); assert r.status_code == 402
    assert sql("SELECT COUNT(*) FROM rides")[0][0] == 0 and sql("SELECT status FROM drivers WHERE id=1")[0][0] == "available"

def test_coupon_validate_apply_once_and_restore_on_cancel(client, auth):
    h = auth("c1@test.in")
    v = client.post("/api/coupons/validate", headers=h, json={"code": "welcome50", "amount": 300, "scope": "ride"}).json()
    assert v["valid"] and v["discount"] == 75
    assert not client.post("/api/coupons/validate", headers=h, json={"code": "SHOP100", "amount": 900, "scope": "ride"}).json()["valid"]   # wrong scope
    r = client.post("/api/rides", headers=h, json={**RIDE, "coupon": "WELCOME50"}).json(); assert r["discount"] > 0 and r["payable"] == round(r["fare"] - r["discount"], 2)
    assert not client.post("/api/coupons/validate", headers=h, json={"code": "WELCOME50", "amount": 300, "scope": "ride"}).json()["valid"]    # one-time
    client.post(f"/api/rides/{r['id']}/cancel", headers=h, json={})
    assert client.post("/api/coupons/validate", headers=h, json={"code": "WELCOME50", "amount": 300, "scope": "ride"}).json()["valid"]        # given back

def test_parcel_flow_with_pickup_and_delivery_otp(client, auth):
    h, d3 = auth("c1@test.in"), auth("d3@test.in")
    est = client.post("/api/parcels/estimate", headers=h, json=PARCEL).json(); assert [o["vehicle_class"] for o in est["options"]] == ["pbike", "pmini", "pvan"]
    r = client.post("/api/parcels", headers=h, json=PARCEL).json(); rid = r["id"]
    assert r["kind"] == "parcel" and r["status"] == "matched" and r["driver"]["id"] == 3 and r["otp"] and r["delivery_otp"]
    assert client.post(f"/api/rides/{rid}/arrived", headers=d3).status_code == 200
    assert client.post(f"/api/rides/{rid}/start", headers=d3, json={"otp": r["otp"]}).status_code == 200
    assert client.post(f"/api/rides/{rid}/complete", headers=d3).status_code == 401                                   # delivery OTP required
    bad = "0000" if r["delivery_otp"] != "0000" else "1111"
    assert client.post(f"/api/rides/{rid}/complete", headers=d3, json={"otp": bad}).status_code == 401
    done = client.post(f"/api/rides/{rid}/complete", headers=d3, json={"otp": r["delivery_otp"]}); assert done.status_code == 200 and done.json()["status"] == "completed"

def test_parcel_validation(client, auth):
    h = auth("c1@test.in")
    assert client.post("/api/parcels", headers=h, json={**PARCEL, "weight_kg": 200, "vehicle_class": "pbike"}).status_code == 400
    assert client.post("/api/parcels", headers=h, json={**PARCEL, "recipient_phone": ""}).status_code == 400

def test_wrong_otp_attempts_are_limited(client, auth):
    h, d1 = auth("c1@test.in"), auth("d1@test.in"); r = client.post("/api/rides", headers=h, json=RIDE).json()
    client.post(f"/api/rides/{r['id']}/arrived", headers=d1); bad = "0000" if r["otp"] != "0000" else "1111"
    for _ in range(5): assert client.post(f"/api/rides/{r['id']}/start", headers=d1, json={"otp": bad}).status_code == 401
    assert client.post(f"/api/rides/{r['id']}/start", headers=d1, json={"otp": r["otp"]}).status_code == 429

def test_demo_autopilot_completes_trip_and_driver_earns(client, auth, sql):
    h, d1 = auth("c1@test.in"), auth("d1@test.in"); r = client.post("/api/rides", headers=h, json=RIDE).json()
    sql("UPDATE rides SET matched_at=matched_at-1000 WHERE id=?", (r["id"],))                                # pretend 1000 s passed
    t = client.get(f"/api/rides/{r['id']}/track", headers=h).json(); assert t["status"] == "completed" and t["otp"] is None
    assert sql("SELECT status FROM drivers WHERE id=1")[0][0] == "available"
    e = client.get("/api/driver/earnings", headers=d1).json(); assert e["total"]["trips"] == 1 and e["total"]["earnings"] == round(r["fare"] * 0.8, 2)
    assert client.get("/api/driver/job", headers=d1).json()["job"] is None

def test_rating_once_and_driver_average_updates(client, auth, sql):
    h = auth("c1@test.in"); r = client.post("/api/rides", headers=h, json=RIDE).json()
    assert client.post(f"/api/rides/{r['id']}/rate", headers=h, json={"rating": 5}).status_code == 409           # not completed yet
    sql("UPDATE rides SET matched_at=matched_at-1000 WHERE id=?", (r["id"],)); client.get(f"/api/rides/{r['id']}/track", headers=h)
    assert client.post(f"/api/rides/{r['id']}/rate", headers=h, json={"rating": 5, "review": "great"}).status_code == 200
    assert client.post(f"/api/rides/{r['id']}/rate", headers=h, json={"rating": 1}).status_code == 409
    assert abs(sql("SELECT capacity_rating FROM drivers WHERE id=1")[0][0] - (4.5 * 5 + 5) / 6) < 0.01

def test_driver_offline_gets_no_trips(client, auth):
    d1 = auth("d1@test.in"); assert client.post("/api/driver/online", headers=d1, json={"online": False}).status_code == 200
    assert client.post("/api/rides", headers=auth("c1@test.in"), json=RIDE).json()["status"] == "searching"

def test_nearby_drivers_hide_identity(client, auth):
    r = client.get("/api/drivers/nearby", headers=auth("c1@test.in"), params={"lat": 26.9, "lng": 75.8, "cls": "cab"}).json()
    assert len(r) >= 1 and set(r[0]) == {"lat", "lng", "eta_min"}

def test_otp_visible_only_to_the_customer(client, auth):
    h, h2, d1 = auth("c1@test.in"), auth("c2@test.in"), auth("d1@test.in"); r = client.post("/api/rides", headers=h, json=RIDE).json()
    assert client.get("/api/rides", headers=h).json()[0]["otp"] == r["otp"]
    assert "otp" not in client.get("/api/rides", headers=d1).json()[0]
    assert client.get(f"/api/rides/{r['id']}/track", headers=h2).status_code == 404
    assert client.get("/api/driver/job", headers=d1).json()["job"]["otp"] is None

def test_late_cancel_charges_fee(client, auth):
    h, d1 = auth("c1@test.in"), auth("d1@test.in"); topup(client, h, 500)
    r = client.post("/api/rides", headers=h, json={**RIDE, "payment_method": "wallet"}).json()
    client.post(f"/api/rides/{r['id']}/arrived", headers=d1)
    c = client.post(f"/api/rides/{r['id']}/cancel", headers=h, json={}).json(); assert c["fee"] == 20.0 and abs(balance(client, h) - (500 - 20)) < 0.01

def test_shop_order_with_wallet_and_coupon(client, auth, sql):
    h = auth("c1@test.in"); topup(client, h, 1000)
    r = client.post("/api/orders", headers=h, json={"address_id": 1, "items": [{"item_id": 2, "quantity": 1}], "payment_method": "wallet", "coupon": "SHOP100"}).json()
    assert r["total"] == 800 and r["discount"] == 100 and balance(client, h) == 200
    assert client.patch(f"/api/orders/{r['id']}/cancel", headers=h).status_code == 200
    assert balance(client, h) == 1000 and sql("SELECT stock FROM items WHERE id=2")[0][0] == 5

def test_admin_can_deactivate_user_but_not_self(client, auth):
    a = auth("admin@test.in")
    assert client.patch("/api/admin/users/1/active", headers=a, json={"active": False}).status_code == 200
    assert client.post("/api/auth/login", json={"email": "c1@test.in", "password": "Demo@123"}).status_code == 401
    assert client.patch("/api/admin/users/3/active", headers=a, json={"active": False}).status_code == 400
