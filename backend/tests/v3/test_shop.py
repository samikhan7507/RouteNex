import uuid

from conftest import window


def put_cart(client, headers, product_id, quantity=1):
    r = client.put("/api/cart", json={"product_id": product_id, "quantity": quantity}, headers=headers)
    assert r.status_code == 200, r.text


def checkout(client, headers, address_id, method="cod", coupon=None, key=None):
    start, end = window()
    body = {"address_id": address_id, "payment_method": method, "delivery_window_start": start,
            "delivery_window_end": end, "idempotency_key": key or str(uuid.uuid4())}
    if coupon:
        body["coupon"] = coupon
    return client.post("/api/orders", json=body, headers=headers)


def test_cod_checkout_idempotency_and_stock(client, seed, login, db):
    headers = login("cust@test.in")
    product = seed["products"][0]
    put_cart(client, headers, product.id, 2)
    key = str(uuid.uuid4())
    r = checkout(client, headers, seed["address"].id, key=key)
    assert r.status_code == 201, r.text
    order = r.json()
    assert order["status"] == "placed"
    assert order["payment_method"] == "cod"
    assert order["delivery_otp"] and len(order["delivery_otp"]) == 6
    again = checkout(client, headers, seed["address"].id, key=key)
    assert again.status_code in (200, 201)
    assert again.json()["id"] == order["id"]
    db.expire_all()
    assert db.get(type(product), product.id).stock == 18
    assert client.get("/api/cart", headers=headers).json()["items"] == []


def test_coupon_cap_and_delivery_fee(client, seed, login):
    headers = login("cust@test.in")
    rice = seed["products"][1]  # ₹600
    put_cart(client, headers, rice.id, 1)
    r = checkout(client, headers, seed["address"].id, coupon="WELCOME50")
    assert r.status_code == 201, r.text
    o = r.json()
    assert o["discount"] == 75.0  # 50% capped at ₹75
    assert o["delivery_fee"] == 0  # subtotal >= ₹499
    assert o["total"] == 525.0


def test_insufficient_stock_and_empty_cart(client, seed, login):
    headers = login("cust@test.in")
    assert checkout(client, headers, seed["address"].id).status_code == 409
    put_cart(client, headers, seed["products"][0].id, 21)
    r = checkout(client, headers, seed["address"].id)
    assert r.status_code == 409


def test_naive_delivery_window_rejected(client, seed, login):
    headers = login("cust@test.in")
    put_cart(client, headers, seed["products"][0].id)
    r = client.post("/api/orders", json={"address_id": seed["address"].id,
        "delivery_window_start": "2026-11-13T09:00:00", "delivery_window_end": "2026-11-13T18:00:00",
        "idempotency_key": str(uuid.uuid4())}, headers=headers)
    assert r.status_code == 422


def test_cancel_restores_stock(client, seed, login, db):
    headers = login("cust@test.in")
    product = seed["products"][0]
    put_cart(client, headers, product.id, 3)
    order = checkout(client, headers, seed["address"].id).json()
    r = client.post(f"/api/orders/{order['id']}/cancel", json={"reason": "Changed my plans"}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "cancelled"
    db.expire_all()
    assert db.get(type(product), product.id).stock == 20


def test_prepaid_demo_capture_and_failure(client, seed, login, db):
    headers = login("cust@test.in")
    product = seed["products"][0]
    put_cart(client, headers, product.id, 1)
    order = checkout(client, headers, seed["address"].id, method="razorpay").json()
    assert order["status"] == "awaiting_payment"
    co = client.post("/api/payments/checkout", json={"purpose": "order", "reference_id": order["id"],
                     "idempotency_key": str(uuid.uuid4())}, headers=headers)
    assert co.status_code == 201, co.text
    pay = co.json()
    assert pay["provider"] == "demo"
    ok = client.post(f"/api/payments/{pay['id']}/demo", json={"outcome": "success"}, headers=headers)
    assert ok.status_code == 200, ok.text
    detail = client.get(f"/api/orders/{order['id']}", headers=headers).json()
    assert detail["status"] == "placed"
    assert detail["payment_status"] == "paid"
    db.expire_all()
    assert db.get(type(product), product.id).reserved == 0

    put_cart(client, headers, product.id, 1)
    order2 = checkout(client, headers, seed["address"].id, method="razorpay").json()
    co2 = client.post("/api/payments/checkout", json={"purpose": "order", "reference_id": order2["id"],
                      "idempotency_key": str(uuid.uuid4())}, headers=headers).json()
    bad = client.post(f"/api/payments/{co2['id']}/demo", json={"outcome": "failure"}, headers=headers)
    assert bad.status_code == 200
    failed = client.get(f"/api/orders/{order2['id']}", headers=headers).json()
    assert failed["status"] == "failed"
    db.expire_all()
    assert db.get(type(product), product.id).reserved == 0
