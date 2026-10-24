import os, sys, pathlib, sqlite3
ROOT = pathlib.Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "backend"))
TEST_DB = ROOT / "database" / "test.db"
os.environ.update(ROUTENEX_DB=str(TEST_DB), ROUTENEX_SECRET="test-secret-value", DEMO_MODE="true", DEMO_AUTOPILOT="true", ROUTENEX_OFFLINE="1", ROUTENEX_ML_AUTOTRAIN="0", LLM_PROVIDER="offline", ROUTENEX_ML_DIR=str(ROOT / "database" / "test_ml_empty"))
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from security import hash_password
import db, app as appmod
from routers import auth as auth_router, rides as rides_router

PW = hash_password("Demo@123")   # hash once, reuse for every fixture user


@pytest.fixture(scope="session")
def client():
    return TestClient(appmod.app)


@pytest.fixture(autouse=True)
def fresh_db():
    for f in (TEST_DB, TEST_DB.with_name("test.db-wal"), TEST_DB.with_name("test.db-shm")):
        f.unlink(missing_ok=True)
    db.init_db()                                   # schema + migrations, exactly like production
    c = sqlite3.connect(TEST_DB)
    U = lambda n, e, r, p=None: c.execute("INSERT INTO users(name,email,phone,password_hash,role) VALUES(?,?,?,?,?)", (n, e, p, PW, r))
    U("Cust1", "c1@test.in", "customer", "8882846897"); U("Cust2", "c2@test.in", "customer")           # ids 1,2
    U("Admin", "admin@test.in", "admin"); U("Disp", "disp@test.in", "dispatcher")                       # 3,4
    U("Drv1", "d1@test.in", "driver"); U("Drv2", "d2@test.in", "driver"); U("Drv3", "d3@test.in", "driver")  # 5,6,7
    V = lambda plate, typ, cap, lat, lng: c.execute("INSERT INTO vehicles(plate,type,capacity_kg,lat,lng) VALUES(?,?,?,?,?)", (plate, typ, cap, lat, lng))
    V("V1", "Cab", 20, 26.9, 75.8); V("V2", "Van", 900, 26.3, 75.1); V("V3", "Bike", 30, 26.9, 75.8)  # V2 is far away
    for uid, vid, lat, lng in ((5, 1, 26.9, 75.8), (6, 2, 26.3, 75.1), (7, 3, 26.9, 75.8)):
        c.execute("INSERT INTO drivers(user_id,license,available,status,lat,lng,vehicle_id,capacity_rating) VALUES(?,?,1,'available',?,?,?,4.5)", (uid, f"L{uid}", lat, lng, vid))
    c.execute("INSERT INTO items(name,description,category,price,stock,icon) VALUES('Parcel','x','Delivery',100,10,'P')")
    c.execute("INSERT INTO items(name,description,category,price,stock,icon) VALUES('Crate','x','Moving',900,5,'C')")
    for uid in (1, 2):
        c.execute("INSERT INTO addresses(user_id,label,line1,city,state,pincode,lat,lng) VALUES(?,'Home','A road','Jaipur','RJ','302001',26.91,75.79)", (uid,))
    c.commit(); c.close()
    from routers import assistant as assistant_router
    assistant_router.limiter.hits.clear()
    for lim in (auth_router.login_limiter, auth_router.otp_req_limiter, auth_router.otp_ver_limiter, rides_router.otp_limiter):
        lim.hits.clear()


@pytest.fixture
def auth(client):
    def _a(email):
        r = client.post("/api/auth/login", json={"email": email, "password": "Demo@123"}); assert r.status_code == 200, r.text
        return {"Authorization": "Bearer " + r.json()["access_token"]}
    return _a


@pytest.fixture
def sql():
    def _q(q, a=()):
        c = sqlite3.connect(TEST_DB); c.row_factory = sqlite3.Row
        r = c.execute(q, a).fetchall(); c.commit(); c.close(); return r
    return _q


# ---------- ML test helpers ----------
EMPTY_ML = ROOT / "database" / "test_ml_empty"


@pytest.fixture(scope="session")
def ml_trained(tmp_path_factory):
    from ml import train
    d = tmp_path_factory.mktemp("ml_models")
    train.run(d, n_eta=12000, n_delay=9000, days=70, log=lambda *a: None)
    return d


@pytest.fixture
def use_models(ml_trained):
    from services import mlserve
    mlserve.ART = ml_trained; mlserve._state.update(models={}, reg_mtime=0.0, forecast=None)
    yield mlserve
    mlserve.ART = EMPTY_ML; mlserve._state.update(models={}, reg_mtime=0.0, forecast=None)


@pytest.fixture(autouse=True)
def reset_ml_and_weather():
    from services import mlserve, weather
    mlserve.ART = EMPTY_ML; mlserve._state.update(models={}, reg_mtime=0.0, forecast=None, training=False)
    weather._cache.update(at=0.0, data=None)


@pytest.fixture(autouse=True)
def fixed_clock(monkeypatch):
    """The optimizer reads the clock (delivery windows are times of day). Pin it to 12:00 IST so the suite passes at any hour, including after midnight."""
    from routers import ops
    from services.pricing import IST
    monkeypatch.setattr(ops, "_now_ist", lambda: datetime(2026, 10, 19, 12, 0, tzinfo=IST))
