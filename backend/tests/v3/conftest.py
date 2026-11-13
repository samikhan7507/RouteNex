"""PostgreSQL-backed tests for the v3 API. Requires TEST_DATABASE_URL (or the local pgserver socket)."""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

TEST_URL = os.environ.get("TEST_DATABASE_URL") or f"postgresql+psycopg://routenex@/routenex_test?host={ROOT / '.local' / 'postgres'}"
os.environ.update(
    DATABASE_URL=TEST_URL,
    APP_ENV="test",
    BASE_URL="http://testserver",
    TRUSTED_HOSTS="testserver,localhost,127.0.0.1,*.e2b.app",
    SECRET_KEY="routenex-v3-test-secret-key-000000000001",
    DEMO_MODE="true",
    DEMO_AUTOPILOT="false",
    SEED_DEMO_DATA="false",
    PAYMENT_PROVIDER="demo",
    OTP_PROVIDER="console",
    LOCATION_PROVIDER="local",
    WEATHER_ENABLED="false",
    ML_AUTOTRAIN="false",
    ADMIN_EMAIL="admin@test.in",
    ADMIN_PASSWORD="TestAdmin@12345",
)

import pytest
from datetime import datetime, time
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.security import hash_password
from app.db import engine, SessionLocal
from app.models import Address, Base, Coupon, Driver, Product, User, Vehicle
from app.services.pricing import IST

PASSWORD = "Demo@123"
HASH = hash_password(PASSWORD)


@pytest.fixture(scope="session", autouse=True)
def schema():
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, check=True,
                   env={**os.environ, "DATABASE_URL": TEST_URL}, capture_output=True, text=True)
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_db(schema):
    tables = ", ".join(t.name for t in reversed(Base.metadata.sorted_tables))
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


@pytest.fixture
def seed(db):
    users = {}
    for role, email in [("admin", "admin@test.in"), ("customer", "cust@test.in"), ("driver", "driver@test.in"),
                        ("driver", "driver2@test.in"), ("dispatcher", "disp@test.in"), ("fleet_manager", "fleet@test.in")]:
        u = User(name=role.title(), email=email, phone=None, password_hash=HASH, role=role,
                 wallet_balance_paise=100000 if role == "customer" else 0)
        db.add(u)
        db.flush()
        users[email] = u
    customer = users["cust@test.in"]
    address = Address(user_id=customer.id, label="Home", line1="12 Malviya Nagar", city="Jaipur",
                      state="Rajasthan", pincode="302017", lat=26.8540, lng=75.8243)
    db.add(address)
    products = []
    for sku, name, cat, price, stock, grams in [("T-NB", "Test Notebook", "Stationery", 8900, 20, 400),
                                                ("T-RICE", "Test Rice 5kg", "Groceries", 60000, 10, 5000),
                                                ("T-PEN", "Test Pens", "Stationery", 6000, 50, 120)]:
        p = Product(sku=sku, slug=sku.lower(), name=name, description="Test product", category=cat,
                    price_paise=price, stock=stock, weight_grams=grams, image_path="/products/notebook.jpg")
        db.add(p)
        db.flush()
        products.append(p)
    vehicles = []
    for plate, typ, cap in [("RJ14-TST-1", "Bike", 20), ("RJ14-TST-2", "Bike", 25), ("RJ14-TST-3", "Van", 900)]:
        v = Vehicle(plate=plate, type=typ, capacity_kg=cap, cost_per_km_paise=500, status="available",
                    lat=26.8540, lng=75.8243, documents="Verified")
        db.add(v)
        db.flush()
        vehicles.append(v)
    drivers = []
    for i, email in enumerate(["driver@test.in", "driver2@test.in"]):
        d = Driver(user_id=users[email].id, vehicle_id=vehicles[i].id, license_number=f"RJ14-TEST-{i}",
                   documents="Verified", service="both", online=True, status="available", lat=26.8545, lng=75.8240)
        db.add(d)
        db.flush()
        drivers.append(d)
    db.add(Coupon(code="WELCOME50", title="50% off", scope="all", kind="percent", value=50,
                  max_discount_paise=7500, min_amount_paise=10000, one_time=True))
    db.add(Coupon(code="SHOP100", title="₹100 off", scope="shop", kind="flat", value=10000,
                  min_amount_paise=79900, one_time=False))
    db.commit()
    return {"users": users, "customer": customer, "address": address, "products": products,
            "vehicles": vehicles, "drivers": drivers}


@pytest.fixture
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def login(client):
    def _login(email, password=PASSWORD):
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return {"X-CSRF-Token": r.json()["csrf_token"]}
    return _login


@pytest.fixture
def role_client():
    from app.main import app
    clients = []
    def _make(email, password=PASSWORD):
        c = TestClient(app)
        clients.append(c)
        r = c.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return c, {"X-CSRF-Token": r.json()["csrf_token"]}
    yield _make
    for c in clients:
        c.close()


def window(day_offset=0):
    day = datetime.now(IST).date()
    from datetime import timedelta
    day = day + timedelta(days=day_offset)
    start = datetime.combine(day, time(0, 0), IST)
    end = datetime.combine(day, time(23, 59, 59), IST)
    return start.isoformat(), end.isoformat()
