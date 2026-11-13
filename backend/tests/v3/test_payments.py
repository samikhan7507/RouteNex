import uuid

from conftest import window


def test_wallet_topup_demo_and_ledger(client, seed, login):
    headers = login("cust@test.in")
    before = client.get("/api/wallet", headers=headers).json()["balance"]
    co = client.post("/api/payments/checkout", json={"purpose": "wallet_topup", "amount": "250.00",
                     "idempotency_key": str(uuid.uuid4())}, headers=headers)
    assert co.status_code == 201, co.text
    pay = co.json()
    assert client.post(f"/api/payments/{pay['id']}/demo", json={"outcome": "success"}, headers=headers).status_code == 200
    wallet = client.get("/api/wallet", headers=headers).json()
    assert wallet["balance"] == before + 250.0
    assert any(t["kind"] == "topup" for t in wallet["transactions"])


def test_wallet_purchase_and_admin_refund(client, seed, login, role_client):
    headers = login("cust@test.in")
    start, end = window()
    client.put("/api/cart", json={"product_id": seed["products"][0].id, "quantity": 1}, headers=headers)
    order = client.post("/api/orders", json={"address_id": seed["address"].id, "payment_method": "wallet",
        "delivery_window_start": start, "delivery_window_end": end, "idempotency_key": str(uuid.uuid4())}, headers=headers).json()
    assert order["payment_status"] == "paid"
    balance_after = client.get("/api/wallet", headers=headers).json()["balance"]
    history = client.get("/api/payments", headers=headers).json()
    pay = next(p for p in history if p["purpose"] == "order" and p["provider"] == "wallet")
    admin, ah = role_client("admin@test.in")
    r = admin.post(f"/api/payments/{pay['id']}/refund", json={"reason": "Customer requested refund"}, headers=ah)
    assert r.status_code == 200, r.text
    assert client.get("/api/wallet", headers=headers).json()["balance"] == balance_after + order["total"]


def test_cash_refund_requires_physical_return(client, seed, login, role_client):
    headers = login("cust@test.in")
    q = client.post("/api/trips/quote", json={"kind": "ride",
        "pickup": {"name": "Malviya Nagar", "lat": 26.854, "lng": 75.8243},
        "drop": {"name": "Vaishali Nagar", "lat": 26.9126, "lng": 75.7442}}, headers=headers).json()
    t = client.post("/api/trips", json={"quote_token": q["quote_token"], "vehicle_class": "bike",
        "payment_method": "cash", "idempotency_key": str(uuid.uuid4())}, headers=headers).json()
    driver, dh = role_client("driver@test.in")
    driver.post(f"/api/driver/requests/{t['id']}/accept", headers=dh)
    driver.post(f"/api/driver/trips/{t['id']}/arrive", headers=dh)
    otp = client.get(f"/api/trips/{t['id']}", headers=headers).json()["pickup_otp"]
    driver.post(f"/api/driver/trips/{t['id']}/start", json={"code": otp}, headers=dh)
    driver.post(f"/api/driver/trips/{t['id']}/complete", headers=dh)
    pay = next(p for p in client.get("/api/payments", headers=headers).json()
               if p["purpose"] == "trip" and p["provider"] == "cash" and p["status"] == "captured")
    admin, ah = role_client("admin@test.in")
    missing = admin.post(f"/api/payments/{pay['id']}/refund", json={"reason": "Duplicate cash collection"}, headers=ah)
    assert missing.status_code == 422
    ok = admin.post(f"/api/payments/{pay['id']}/refund",
                    json={"reason": "Duplicate cash collection", "cash_returned": True}, headers=ah)
    assert ok.status_code == 200, ok.text


def test_razorpay_webhook_disabled_in_demo(client):
    r = client.post("/api/payments/webhooks/razorpay", content=b"{}", headers={"x-razorpay-signature": "bad"})
    assert r.status_code == 409


def test_checkout_idempotency_key_reuse_conflict(client, seed, login):
    headers = login("cust@test.in")
    key = str(uuid.uuid4())
    a = client.post("/api/payments/checkout", json={"purpose": "wallet_topup", "amount": "100",
                    "idempotency_key": key}, headers=headers)
    assert a.status_code == 201
    b = client.post("/api/payments/checkout", json={"purpose": "wallet_topup", "amount": "200",
                    "idempotency_key": key}, headers=headers)
    assert b.status_code in (200, 201)
    assert b.json()["id"] == a.json()["id"]  # same key returns the original checkout, never a second charge
