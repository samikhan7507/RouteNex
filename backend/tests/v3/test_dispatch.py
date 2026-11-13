import uuid

from conftest import window


def make_order(client, headers, address_id, product_id, quantity=1):
    start, end = window()
    client.put("/api/cart", json={"product_id": product_id, "quantity": quantity}, headers=headers)
    r = client.post("/api/orders", json={"address_id": address_id, "payment_method": "cod",
        "delivery_window_start": start, "delivery_window_end": end, "idempotency_key": str(uuid.uuid4())}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def test_preview_apply_exact_and_no_double_apply(client, seed, login, role_client):
    ch = login("cust@test.in")
    o1 = make_order(client, ch, seed["address"].id, seed["products"][0].id)
    o2 = make_order(client, ch, seed["address"].id, seed["products"][2].id)
    disp, dh = role_client("disp@test.in")
    preview = disp.post("/api/optimizer/preview", json={"traffic_factor": 1.0, "time_limit_seconds": 0.5}, headers=dh)
    assert preview.status_code == 200, preview.text
    plan = preview.json()
    assert plan["routes"], plan
    planned_orders = {s["order_id"] for r in plan["routes"] for s in r["stops"]}
    assert {o1["id"], o2["id"]} <= planned_orders
    apply = disp.post("/api/optimizer/apply", json={"plan_id": plan["plan_id"]}, headers=dh)
    assert apply.status_code == 200, apply.text
    assert apply.json()["exact_preview"] is True
    assert len(apply.json()["route_ids"]) == len(plan["routes"])
    for oid in (o1["id"], o2["id"]):
        assert client.get(f"/api/orders/{oid}", headers=ch).json()["status"] == "assigned"
    again = disp.post("/api/optimizer/apply", json={"plan_id": plan["plan_id"]}, headers=dh)
    assert again.status_code == 409


def test_stale_preview_is_rejected(client, seed, login, role_client):
    ch = login("cust@test.in")
    make_order(client, ch, seed["address"].id, seed["products"][0].id)
    disp, dh = role_client("disp@test.in")
    plan = disp.post("/api/optimizer/preview", json={"traffic_factor": 1.0, "time_limit_seconds": 0.5}, headers=dh).json()
    make_order(client, ch, seed["address"].id, seed["products"][2].id)  # state changes after preview
    stale = disp.post("/api/optimizer/apply", json={"plan_id": plan["plan_id"]}, headers=dh)
    assert stale.status_code == 409


def test_customer_cannot_dispatch(client, seed, login):
    headers = login("cust@test.in")
    r = client.post("/api/optimizer/preview", json={"traffic_factor": 1.0, "time_limit_seconds": 0.5}, headers=headers)
    assert r.status_code == 403
