import uuid

PICKUP = {"name": "Malviya Nagar", "lat": 26.8540, "lng": 75.8243}
DROP = {"name": "Vaishali Nagar", "lat": 26.9126, "lng": 75.7442}


def quote(client, headers, kind="ride", weight=1):
    r = client.post("/api/trips/quote", json={"kind": kind, "pickup": PICKUP, "drop": DROP,
                    "weight_kg": weight, "parcel_size": "small", "fragile": False}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def book(client, headers, q, cls, method="cash", **extra):
    body = {"quote_token": q["quote_token"], "vehicle_class": cls, "payment_method": method,
            "idempotency_key": str(uuid.uuid4()), **extra}
    return client.post("/api/trips", json=body, headers=headers)


def test_ride_cash_lifecycle_with_proof_and_earnings(client, seed, login, role_client):
    headers = login("cust@test.in")
    q = quote(client, headers)
    assert {x["vehicle_class"] for x in q["quotes"]} == {"bike", "auto", "cab"}
    r = book(client, headers, q, "bike")
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["status"] == "searching"
    assert t["pickup_otp"] and len(t["pickup_otp"]) == 6

    driver, dh = role_client("driver@test.in")
    reqs = driver.get("/api/driver/requests", headers=dh)
    assert reqs.status_code == 200
    assert t["id"] in [x["id"] for x in reqs.json()]
    acc = driver.post(f"/api/driver/requests/{t['id']}/accept", headers=dh)
    assert acc.status_code == 200, acc.text
    assert acc.json()["status"] == "matched"
    assert driver.post(f"/api/driver/trips/{t['id']}/arrive", headers=dh).status_code == 200

    otp = client.get(f"/api/trips/{t['id']}", headers=headers).json()["pickup_otp"]
    bad = driver.post(f"/api/driver/trips/{t['id']}/start", json={"code": "000000"}, headers=dh)
    assert bad.status_code == 400
    assert driver.post(f"/api/driver/trips/{t['id']}/start", json={"code": otp}, headers=dh).status_code == 200
    done = driver.post(f"/api/driver/trips/{t['id']}/complete", headers=dh)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"
    assert done.json()["payment_status"] == "paid"  # cash settled only on completion

    earn = driver.get("/api/driver/earnings", headers=dh).json()
    assert earn["entries"][0]["net"] == round(t["total"] * 0.8, 2)
    assert earn["commission_rate"] == 0.20
    rate = client.post(f"/api/trips/{t['id']}/rate", json={"rating": 5, "review": "Great"}, headers=headers)
    assert rate.status_code == 200, rate.text


def test_parcel_requires_recipient_and_delivery_proof(client, seed, login, role_client):
    headers = login("cust@test.in")
    q = quote(client, headers, kind="parcel")
    missing = book(client, headers, q, "pbike")
    assert missing.status_code == 422
    r = book(client, headers, q, "pbike", recipient_name="Recipient", recipient_phone="+919876500003")
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["delivery_otp"] and len(t["delivery_otp"]) == 6

    driver, dh = role_client("driver@test.in")
    assert driver.post(f"/api/driver/requests/{t['id']}/accept", headers=dh).status_code == 200
    assert driver.post(f"/api/driver/trips/{t['id']}/arrive", headers=dh).status_code == 200
    pickup_otp = client.get(f"/api/trips/{t['id']}", headers=headers).json()["pickup_otp"]
    assert driver.post(f"/api/driver/trips/{t['id']}/start", json={"code": pickup_otp}, headers=dh).status_code == 200
    no_proof = driver.post(f"/api/driver/trips/{t['id']}/complete", json={"code": "000000"}, headers=dh)
    assert no_proof.status_code == 400
    delivery_otp = client.get(f"/api/trips/{t['id']}", headers=headers).json()["delivery_otp"]
    done = driver.post(f"/api/driver/trips/{t['id']}/complete", json={"code": delivery_otp}, headers=dh)
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "completed"


def test_quote_is_signed_and_user_bound(client, seed, login, role_client):
    headers = login("cust@test.in")
    q = quote(client, headers)
    raw, sig = q["quote_token"].split(".")
    tampered = raw[:-4] + ("AAAA" if raw[-4:] != "AAAA" else "BBBB") + "." + sig
    r = client.post("/api/trips", json={"quote_token": tampered, "vehicle_class": "bike",
                    "payment_method": "cash", "idempotency_key": str(uuid.uuid4())}, headers=headers)
    assert r.status_code == 409
    admin, ah = role_client("admin@test.in")
    other = book(admin, ah, q, "bike")
    assert other.status_code == 409


def test_active_ride_limit(client, seed, login):
    headers = login("cust@test.in")
    q = quote(client, headers)
    assert book(client, headers, q, "bike").status_code == 201
    second = book(client, headers, quote(client, headers), "bike")
    assert second.status_code == 409


def test_prepaid_cancel_refunds(client, seed, login):
    headers = login("cust@test.in")
    q = quote(client, headers)
    t = book(client, headers, q, "bike", method="razorpay").json()
    assert t["status"] == "awaiting_payment"
    co = client.post("/api/payments/checkout", json={"purpose": "trip", "reference_id": t["id"],
                     "idempotency_key": str(uuid.uuid4())}, headers=headers).json()
    assert client.post(f"/api/payments/{co['id']}/demo", json={"outcome": "success"}, headers=headers).status_code == 200
    paid = client.get(f"/api/trips/{t['id']}", headers=headers).json()
    assert paid["status"] == "searching" and paid["payment_status"] == "paid"
    cancel = client.post(f"/api/trips/{t['id']}/cancel", json={"reason": "Plans changed"}, headers=headers)
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "cancelled"
    assert cancel.json()["payment_status"] == "refunded"
