import sqlite3, contextlib
from config import DB_PATH, ROOT


def _connect():
    c = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    c.execute("PRAGMA busy_timeout=15000")
    return c


@contextlib.contextmanager
def tx():
    """One atomic transaction. Commits on success, rolls back on any exception, always closes."""
    c = _connect()
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def rows(sql, args=()):
    c = _connect()
    try:
        return [dict(x) for x in c.execute(sql, args).fetchall()]
    finally:
        c.close()


def one(sql, args=()):
    c = _connect()
    try:
        x = c.execute(sql, args).fetchone()
        return dict(x) if x else None
    finally:
        c.close()


def run(sql, args=()):
    with tx() as c:
        return c.execute(sql, args).lastrowid


def audit(user_id, action, entity, entity_id="", details=""):
    run("INSERT INTO audit_logs(user_id,action,entity,entity_id,details) VALUES(?,?,?,?,?)",
        (user_id, action, entity, str(entity_id), details))


# Additive, idempotent migrations: (table, column, DDL). Works on old databases AND fresh ones.
MIGRATIONS = [
    ("rides", "kind", "TEXT DEFAULT 'ride'"), ("rides", "vehicle_class", "TEXT DEFAULT 'cab'"), ("rides", "otp", "TEXT"),
    ("rides", "payment_method", "TEXT DEFAULT 'cash'"), ("rides", "payment_status", "TEXT DEFAULT 'pending'"),
    ("rides", "paid_amount", "REAL DEFAULT 0"), ("rides", "discount", "REAL DEFAULT 0"), ("rides", "surge", "REAL DEFAULT 1"),
    ("rides", "coupon", "TEXT"), ("rides", "search_started_at", "INTEGER"), ("rides", "matched_at", "INTEGER"),
    ("rides", "arrived_at", "INTEGER"), ("rides", "started_at", "INTEGER"), ("rides", "completed_at", "INTEGER"),
    ("rides", "drv_lat", "REAL"), ("rides", "drv_lng", "REAL"), ("rides", "approach_km", "REAL"), ("rides", "sim", "INTEGER DEFAULT 0"),
    ("rides", "rating", "INTEGER"), ("rides", "review", "TEXT"), ("rides", "cancel_reason", "TEXT"),
    ("drivers", "rating_count", "INTEGER DEFAULT 5"), ("drivers", "online", "INTEGER DEFAULT 1"), ("drivers", "service", "TEXT DEFAULT 'both'"),
    ("users", "wallet_balance", "REAL DEFAULT 0"),
    ("orders", "discount", "REAL DEFAULT 0"), ("orders", "payment_method", "TEXT DEFAULT 'cod'"),
    ("orders", "payment_status", "TEXT DEFAULT 'pending'"), ("orders", "paid_amount", "REAL DEFAULT 0"), ("orders", "coupon", "TEXT"),
    ("items", "weight_kg", "REAL"), ("orders", "weight_kg", "REAL"),
    ("routes", "load_kg", "REAL"), ("routes", "method", "TEXT"), ("routes", "saved_km", "REAL"), ("route_orders", "arrival_min", "INTEGER"), ("route_orders", "delay_risk", "REAL"),
]
ITEM_WEIGHTS = {"Express Parcel": 2, "Same-Day Documents": 0.3, "Grocery Essentials Box": 8, "Pharmacy Express": 0.5, "Cold Chain Crate": 12,
                "Home Move Mini": 300, "Home Move Plus": 900, "Electronics Secure": 6, "Fragile Art Pack": 15, "Bulk Business Van": 400,
                "Two-Wheeler Tow": 150, "Airport Luggage": 20, "Furniture Delivery": 120, "Food Partner Sprint": 1.5, "Daily Delivery Pass": 1}
DEFAULT_COUPONS = [  # code, title, scope, kind, value, max_discount, min_amount, one_time
    ("WELCOME50", "50% off your first trip, up to Rs 75", "all", "percent", 50, 75, 100, 1),
    ("RIDE20", "20% off rides, up to Rs 60", "ride", "percent", 20, 60, 80, 0),
    ("PARCEL25", "Flat Rs 25 off parcels", "parcel", "flat", 25, None, 120, 0),
    ("SHOP100", "Flat Rs 100 off orders above Rs 799", "shop", "flat", 100, None, 799, 0),
]


def migrate(c):
    for table, col, ddl in MIGRATIONS:
        have = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
        if col not in have:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    c.execute("CREATE INDEX IF NOT EXISTS idx_rides_kind ON rides(kind, status)")
    for name, w in ITEM_WEIGHTS.items():                 # real weights drive vehicle capacity in the optimizer
        c.execute("UPDATE items SET weight_kg=? WHERE name=? AND weight_kg IS NULL", (w, name))
    c.execute("""UPDATE orders SET weight_kg=(SELECT SUM(oi.quantity*COALESCE(i.weight_kg,2)) FROM order_items oi JOIN items i ON i.id=oi.item_id
                 WHERE oi.order_id=orders.id) WHERE weight_kg IS NULL""")
    for row in DEFAULT_COUPONS:
        c.execute("INSERT OR IGNORE INTO coupons(code,title,scope,kind,value,max_discount,min_amount,one_time) VALUES(?,?,?,?,?,?,?,?)", row)


def init_db():
    """Create tables/indexes if missing, then apply migrations (safe to run on every start)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = _connect()
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript((ROOT / "database" / "schema.sql").read_text(encoding="utf-8"))
        migrate(c)
        c.commit()
    finally:
        c.close()
