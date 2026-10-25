"""Demo-mode top-ups that run at startup (idempotent): ride fleet around Jaipur + welcome wallet credit."""
import os
import config
from db import tx
from security import hash_password, verify_password
from services import trips

LOCS = [(26.9124, 75.7873), (26.8540, 75.8243), (26.9126, 75.7442), (26.8505, 75.7628), (26.8399, 75.8322), (26.8942, 75.8210),
        (26.9322, 75.7933), (26.8735, 75.7950), (26.9227, 75.7994), (26.9196, 75.7881), (26.9064, 75.7790), (26.8530, 75.8056)]
NAMES = ["Rakesh Meena", "Sanjay Gurjar", "Imtiyaz Khan", "Deepak Saini", "Manoj Sharma", "Lokesh Yadav", "Aslam Qureshi", "Vikram Rathore",
         "Pappu Choudhary", "Hemant Jain", "Naveen Verma", "Ramesh Pareek"]


def ensure_demo_data():
    if not config.DEMO_MODE:
        return
    pw = hash_password("Demo@123")
    with tx() as c:
        if not c.execute("SELECT 1 FROM meta WHERE key='demo_ride_fleet_v2'").fetchone():
            spec = [("Bike", "B", 120, 6, 4), ("Auto", "A", 280, 10, 4), ("Cab", "C", 450, 14, 4)]
            n = 0
            for vtype, tag, cap, cost, count in spec:
                for i in range(count):
                    n += 1
                    lat, lng = LOCS[(n * 5 + i) % len(LOCS)]
                    lat, lng = lat + 0.004 * ((i % 3) - 1), lng + 0.004 * (((i + 1) % 3) - 1)
                    plate = f"RJ14-RD-{tag}{i + 1:02d}"
                    c.execute("INSERT OR IGNORE INTO users(name,email,phone,password_hash,role) VALUES(?,?,?,?,'driver')",
                              (NAMES[(n - 1) % len(NAMES)], f"ridedriver{n}@routenex.in", f"90000001{n:02d}", pw))
                    uid = c.execute("SELECT id FROM users WHERE email=?", (f"ridedriver{n}@routenex.in",)).fetchone()[0]
                    c.execute("INSERT OR IGNORE INTO vehicles(plate,type,capacity_kg,available,status,lat,lng,documents,cost_per_km) VALUES(?,?,?,1,'available',?,?,?,?)",
                              (plate, vtype, cap, lat, lng, "RC OK, Insurance OK, PUC OK", cost))
                    vid = c.execute("SELECT id FROM vehicles WHERE plate=?", (plate,)).fetchone()[0]
                    c.execute("""INSERT OR IGNORE INTO drivers(user_id,license,capacity_rating,available,status,lat,lng,documents,vehicle_id,service,online,rating_count)
                                 VALUES(?,?,?,1,'available',?,?,?,?,'ride',1,40)""",
                              (uid, f"RJ14-2025-{n:04d}", round(4.3 + (n % 7) * 0.1, 1), lat, lng, "License OK, Police OK", vid))
            c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('demo_ride_fleet_v2','1')")
        if not c.execute("SELECT 1 FROM meta WHERE key='demo_wallet_v2'").fetchone():
            for r in c.execute("SELECT id FROM users WHERE role='customer' AND wallet_balance=0").fetchall():
                trips.wallet_credit(c, r["id"], 500.0, "topup", "Welcome credit (demo)")
            c.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('demo_wallet_v2','1')")


def ensure_admin():
    """Make the owner's admin login match ADMIN_NAME / ADMIN_EMAIL / ADMIN_PASSWORD (environment variables, never committed to git).
    Safe to run on every start (idempotent):
      * an account with that e-mail is updated in place; otherwise the lowest-id admin is renamed in place, so the old admin
        disappears and every audit-trail row now shows the new name; otherwise a new admin is created
      * every OTHER admin account is deactivated, so no public/demo admin login can remain
    Does nothing unless both ADMIN_EMAIL and ADMIN_PASSWORD are set. Returns the admin's user id (or None)."""
    email = (os.getenv("ADMIN_EMAIL") or "").strip().lower()
    password = os.getenv("ADMIN_PASSWORD") or ""
    name = (os.getenv("ADMIN_NAME") or "Sami Khan").strip()[:60] or "Sami Khan"
    if not email or not password:
        return None
    if len(password) < 8:
        print("WARNING: ADMIN_PASSWORD is shorter than 8 characters - fine on your laptop, but use a longer one before sharing a public link.")
    with tx() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        verb = "updated"
        if not row:
            row = c.execute("SELECT * FROM users WHERE role='admin' ORDER BY id LIMIT 1").fetchone()
            verb = "replaced"
        if row:
            uid = row["id"]
            c.execute("UPDATE users SET name=?,email=?,role='admin',active=1 WHERE id=?", (name, email, uid))
            if not verify_password(password, row["password_hash"] or ""):     # only re-hash when the password actually changed
                c.execute("UPDATE users SET password_hash=? WHERE id=?", (hash_password(password), uid))
        else:
            uid = c.execute("INSERT INTO users(name,email,password_hash,role) VALUES(?,?,?,'admin')", (name, email, hash_password(password))).lastrowid
            verb = "created"
        c.execute("UPDATE users SET active=0 WHERE role='admin' AND id!=?", (uid,))
        c.execute("INSERT INTO audit_logs(user_id,action,entity,entity_id,details) VALUES(?,?,?,?,?)", (uid, "ADMIN_SYNC", "user", str(uid), f"owner admin {verb} from environment"))
    print(f"[admin] owner admin {verb}: {name} <{email}>")
    return uid


def ensure_catalog():
    """Keeps the shop catalogue up to date. The catalogue lives in services/catalog.py (added in a later phase); until that file
    exists this does nothing, so earlier phases keep working on their own."""
    try:
        from services import catalog
    except ImportError:
        return 0
    return catalog.sync()
