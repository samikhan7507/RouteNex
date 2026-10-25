"""Owner/admin identity: the login comes from ADMIN_* environment variables, replaces the old admin in place, and is listed first."""
from security import verify_password
from services import bootstrap

OWNER = {"ADMIN_NAME": "Sami Khan", "ADMIN_EMAIL": "sami@test.in", "ADMIN_PASSWORD": "owner-pass-123"}


def set_owner(monkeypatch, **over):
    for k, v in {**OWNER, **over}.items():
        monkeypatch.setenv(k, v)


def test_owner_replaces_the_existing_admin_in_place(monkeypatch, sql):
    set_owner(monkeypatch)
    uid = bootstrap.ensure_admin()
    assert uid == 3                                                     # the fixture's admin row was renamed, not duplicated
    r = sql("SELECT name,email,role,active,password_hash FROM users WHERE id=3")[0]
    assert (r["name"], r["email"], r["role"], r["active"]) == ("Sami Khan", "sami@test.in", "admin", 1)
    assert verify_password("owner-pass-123", r["password_hash"]) and not verify_password("Demo@123", r["password_hash"])
    assert sql("SELECT COUNT(*) FROM users WHERE email='admin@test.in'")[0][0] == 0


def test_nothing_changes_without_admin_env(monkeypatch, sql):
    for k in OWNER:
        monkeypatch.delenv(k, raising=False)
    assert bootstrap.ensure_admin() is None
    assert sql("SELECT name FROM users WHERE id=3")[0][0] == "Admin"


def test_other_admin_accounts_are_deactivated(monkeypatch, sql):
    sql("INSERT INTO users(name,email,password_hash,role) VALUES('Spare','spare@test.in','x','admin')")
    set_owner(monkeypatch)
    bootstrap.ensure_admin()
    assert sql("SELECT active FROM users WHERE email='spare@test.in'")[0][0] == 0
    assert sql("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1")[0][0] == 1


def test_running_twice_is_harmless_and_a_new_password_is_picked_up(monkeypatch, sql):
    set_owner(monkeypatch)
    bootstrap.ensure_admin()
    h1 = sql("SELECT password_hash FROM users WHERE id=3")[0][0]
    assert bootstrap.ensure_admin() == 3 and sql("SELECT password_hash FROM users WHERE id=3")[0][0] == h1
    monkeypatch.setenv("ADMIN_PASSWORD", "changed-pass-456")
    bootstrap.ensure_admin()
    assert verify_password("changed-pass-456", sql("SELECT password_hash FROM users WHERE id=3")[0][0])


def test_audit_rows_show_the_new_name(monkeypatch, client, auth, sql):
    sql("INSERT INTO audit_logs(user_id,action,entity,entity_id,details) VALUES(3,'LOGIN','user','3','old')")
    set_owner(monkeypatch)
    bootstrap.ensure_admin()
    token = client.post("/api/auth/login", json={"email": "sami@test.in", "password": "owner-pass-123"}).json()["access_token"]
    logs = client.get("/api/audit", headers={"Authorization": "Bearer " + token}).json()
    assert any(l["name"] == "Sami Khan" for l in logs) and not any(l["name"] == "Admin" for l in logs)


def test_admin_is_first_in_users_and_old_admin_login_is_blocked(monkeypatch, client):
    set_owner(monkeypatch)
    bootstrap.ensure_admin()
    token = client.post("/api/auth/login", json={"email": "sami@test.in", "password": "owner-pass-123"}).json()["access_token"]
    users = client.get("/api/admin/users", headers={"Authorization": "Bearer " + token}).json()
    assert users[0]["name"] == "Sami Khan" and users[0]["role"] == "admin"
    assert client.post("/api/auth/login", json={"email": "admin@test.in", "password": "Demo@123"}).status_code == 401
