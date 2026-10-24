"""Demo-mode top-ups that run at startup (idempotent): ride fleet around Jaipur + welcome wallet credit."""
import config
from db import tx
from security import hash_password
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
