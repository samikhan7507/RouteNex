from app.api.auth import DEMO_PHONE


def test_register_login_me_and_csrf(client):
    r = client.post("/api/auth/register", json={"name": "New Customer", "email": "new@test.in", "password": "LongPassword@123"})
    assert r.status_code == 201, r.text
    csrf = r.json()["csrf_token"]
    me = client.get("/api/auth/me", headers={"X-CSRF-Token": csrf})
    assert me.status_code == 200
    assert me.json()["csrf_token"] == csrf  # valid supplied token is reused, not rotated
    ok = client.patch("/api/auth/me", json={"name": "Renamed Customer"}, headers={"X-CSRF-Token": csrf})
    assert ok.status_code == 200
    assert client.patch("/api/auth/me", json={"name": "No CSRF"}).status_code == 403
    assert client.patch("/api/auth/me", json={"name": "Bad Origin"},
                        headers={"X-CSRF-Token": csrf, "Origin": "https://evil.example"}).status_code == 403


def test_short_password_rejected(client):
    r = client.post("/api/auth/register", json={"name": "Weak", "email": "weak@test.in", "password": "short"})
    assert r.status_code == 422


def test_logout_revokes_session(client, seed, login):
    headers = login("cust@test.in")
    assert client.get("/api/auth/me", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_rbac_customer_cannot_admin(client, seed, login):
    headers = login("cust@test.in")
    assert client.get("/api/admin/users", headers=headers).status_code == 403
    client.cookies.clear()
    assert client.get("/api/admin/users").status_code == 401


def test_admin_can_deactivate_and_login_fails(client, seed, role_client):
    admin, ah = role_client("admin@test.in")
    customer_id = seed["customer"].id
    r = admin.patch(f"/api/admin/users/{customer_id}/active", json={"active": False}, headers=ah)
    assert r.status_code == 200, r.text
    bad = client.post("/api/auth/login", json={"email": "cust@test.in", "password": "Demo@123"})
    assert bad.status_code == 401


def test_demo_otp_flow(client):
    r = client.post("/api/auth/otp/request", json={"phone": DEMO_PHONE})
    assert r.status_code == 200
    code = r.json()["demo_code"]
    v = client.post("/api/auth/otp/verify", json={"phone": DEMO_PHONE, "code": code})
    assert v.status_code == 200, v.text
    assert v.json()["user"]["role"] == "customer"
    assert client.get("/api/auth/me", headers={"X-CSRF-Token": v.json()["csrf_token"]}).status_code == 200
