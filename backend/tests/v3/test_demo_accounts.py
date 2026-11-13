"""Regression coverage for the public demo identities and startup seeding contract."""
from __future__ import annotations

import importlib.util
import pathlib
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.core.demo import DEMO_ACCOUNTS, DEMO_ADMIN_EMAIL, DEMO_PASSWORD
from app.core.security import verify_password
from app.models import Driver, Order, Trip, User, Vehicle

ROOT = pathlib.Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("routenex_bootstrap", ROOT / "scripts" / "bootstrap.py")
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


def test_demo_config_matches_the_unified_credentials(client):
    config = client.get("/api/auth/config").json()
    assert config["demo_mode"] is True
    assert config["demo_password"] == DEMO_PASSWORD == "Demo@123"
    assert config["demo_accounts"] == [
        {"label": "Admin", "role": "admin", "email": "samikhan@routenex.in"},
        {"label": "Customer", "role": "customer", "email": "customer@routenex.in"},
        {"label": "Driver", "role": "driver", "email": "driver@routenex.in"},
        {"label": "Dispatcher", "role": "dispatcher", "email": "dispatcher@routenex.in"},
        {"label": "Fleet manager", "role": "fleet_manager", "email": "fleet@routenex.in"},
    ]
    assert all("password_hash" not in account and "phone" not in account for account in config["demo_accounts"])


def test_demo_credentials_are_not_advertised_when_demo_mode_is_off(client, monkeypatch):
    from app.api import auth

    settings = get_settings().model_copy(update={"demo_mode": False})
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    config = client.get("/api/auth/config").json()
    assert config["demo_mode"] is False
    assert config["demo_accounts"] == []
    assert config["demo_password"] is None
    assert config["demo_phone"] is None


def test_seed_flag_without_cli_flag_creates_all_login_accounts(client, db, monkeypatch):
    settings = get_settings().model_copy(update={"seed_demo_data": True})
    monkeypatch.setattr(bootstrap, "get_settings", lambda: settings)
    monkeypatch.setattr("sys.argv", ["bootstrap.py"])
    bootstrap.main()
    db.expire_all()

    for account in DEMO_ACCOUNTS:
        response = client.post("/api/auth/login", json={"email": account["email"], "password": DEMO_PASSWORD})
        assert response.status_code == 200, response.text
        assert response.json()["user"]["email"] == account["email"]
        assert response.json()["user"]["role"] == account["role"]
        client.cookies.clear()

    assert db.scalar(select(func.count(User.id)).where(User.email.in_([a["email"] for a in DEMO_ACCOUNTS]))) == 5
    assert db.scalar(select(func.count(Driver.id))) >= 12
    assert db.scalar(select(func.count(Vehicle.id))) >= 12


def test_demo_seed_is_idempotent_and_keeps_operational_rows(db, monkeypatch):
    settings = get_settings().model_copy(update={"seed_demo_data": True})
    monkeypatch.setattr(bootstrap, "get_settings", lambda: settings)
    monkeypatch.setattr("sys.argv", ["bootstrap.py"])
    bootstrap.main()
    db.expire_all()
    before = {model: db.scalar(select(func.count(model.id))) for model in (User, Order, Trip, Driver, Vehicle)}
    ids = set(db.scalars(select(User.id)))
    bootstrap.main()
    db.expire_all()
    after = {model: db.scalar(select(func.count(model.id))) for model in before}
    assert after == before
    assert set(db.scalars(select(User.id))) == ids


def test_seed_repairs_inactive_or_wrong_password_reserved_account(db, monkeypatch):
    settings = get_settings().model_copy(update={"seed_demo_data": True})
    monkeypatch.setattr(bootstrap, "get_settings", lambda: settings)
    db.add(User(name="Old Customer", email="customer@routenex.in", password_hash=bootstrap.hash_password("OldPassword@123"),
                role="dispatcher", active=False))
    db.commit()
    bootstrap.seed_demo(db)
    db.commit()
    user = db.scalar(select(User).where(User.email == "customer@routenex.in"))
    assert user.role == "customer" and user.active is True
    assert verify_password(DEMO_PASSWORD, user.password_hash)


def test_seed_attaches_phone_only_demo_customer_without_deleting_it(db, monkeypatch):
    settings = get_settings().model_copy(update={"seed_demo_data": True})
    monkeypatch.setattr(bootstrap, "get_settings", lambda: settings)
    existing = User(name="OTP customer", phone="+919876543210", role="customer", wallet_balance_paise=1234)
    db.add(existing)
    db.commit()
    original_id = existing.id
    bootstrap.seed_demo(db)
    db.commit()
    user = db.get(User, original_id)
    assert user.email == "customer@routenex.in"
    assert user.wallet_balance_paise == 1234
    assert verify_password(DEMO_PASSWORD, user.password_hash)


def test_seed_does_not_steal_a_phone_owned_by_another_email(db, monkeypatch):
    settings = get_settings().model_copy(update={"seed_demo_data": True})
    monkeypatch.setattr(bootstrap, "get_settings", lambda: settings)
    other = User(name="Real customer", email="real@example.in", phone="+919876543210", role="customer")
    db.add(other)
    db.commit()
    bootstrap.seed_demo(db)
    db.commit()
    db.refresh(other)
    demo = db.scalar(select(User).where(User.email == "customer@routenex.in"))
    assert other.phone == "+919876543210"
    assert demo.id != other.id and demo.phone is None


def test_demo_seed_refuses_production_and_non_demo_settings(db, monkeypatch):
    monkeypatch.setattr(bootstrap, "get_settings", lambda: SimpleNamespace(is_production=True, demo_mode=True))
    with pytest.raises(SystemExit):
        bootstrap.seed_demo(db)
    monkeypatch.setattr(bootstrap, "get_settings", lambda: SimpleNamespace(is_production=False, demo_mode=False))
    with pytest.raises(SystemExit):
        bootstrap.seed_demo(db)


def test_admin_default_and_seed_identity_are_unified():
    assert Settings.model_fields["admin_email"].default == DEMO_ADMIN_EMAIL
    assert DEMO_ACCOUNTS[0]["email"] == DEMO_ADMIN_EMAIL
