"""Trip engine shared by rides and parcels: matching, payments, coupons, cancel/complete, demo autopilot, live position."""
import math, time, secrets, calendar
import config
from services.errors import ApiError
from services.geo import haversine_km

CLASS_VEHICLES = {
    "bike": ("Bike",), "auto": ("Auto",), "cab": ("Cab",),
    "pbike": ("Bike",), "pmini": ("Electric Cargo", "Mini Van", "EV Van"), "pvan": ("Van", "Pickup", "Mini Van"),
}
SPEED_KMH = {"bike": 30, "auto": 24, "cab": 26, "pbike": 30, "pmini": 24, "pvan": 22}
ACTIVE = ("searching", "matched", "arriving", "started")
MAX_MATCH_KM, SEARCH_TIMEOUT_S, WAIT_AT_PICKUP_S, CANCEL_FEE, DRIVER_SHARE = 25, 90, 6, 20.0, 0.8


def now_s() -> int:
    return int(time.time())


def new_otp(n=4) -> str:
    return f"{secrets.randbelow(10 ** n):0{n}d}"


def _service(cls: str) -> str:
    return "delivery" if cls.startswith("p") else "ride"


# ---------------- market / matching ----------------
def market(c):
    from services import pricing
    waiting = c.execute("SELECT COUNT(*) FROM rides WHERE status='searching'").fetchone()[0]
    free = c.execute("SELECT COUNT(*) FROM drivers WHERE available=1 AND status='available' AND online=1").fetchone()[0]
    from services import mlserve
    sg = round(min(1.8, pricing.surge(pricing.demand_factor(waiting, free)) * mlserve.demand_adjust()), 2)   # live supply/demand x forecast demand
    return sg, pricing.traffic_factor()


def _eligible(c, cls):
    types = CLASS_VEHICLES[cls]
    ph = ",".join("?" * len(types))
    return c.execute(f"""SELECT d.id,d.lat,d.lng FROM drivers d JOIN vehicles v ON v.id=d.vehicle_id
        WHERE d.available=1 AND d.status='available' AND d.online=1 AND d.lat IS NOT NULL
        AND v.type IN ({ph}) AND d.service IN (?, 'both')""", (*types, _service(cls))).fetchall()


def availability(c, cls, lat, lng):
    ranked = sorted(haversine_km(lat, lng, r["lat"], r["lng"]) for r in _eligible(c, cls))
    return sum(1 for k in ranked if k <= 8), (ranked[0] if ranked else None)


def nearby(c, cls, lat, lng, limit=12):
    out = []
    for r in _eligible(c, cls):
        km = haversine_km(lat, lng, r["lat"], r["lng"])
        if km <= 10:
            out.append({"lat": round(r["lat"], 5), "lng": round(r["lng"], 5), "eta_min": max(2, math.ceil(km / SPEED_KMH[cls] * 60))})
    return sorted(out, key=lambda x: x["eta_min"])[:limit]


def claim_driver(c, cls, plat, plng):
    ranked = sorted(((haversine_km(plat, plng, r["lat"], r["lng"]), r) for r in _eligible(c, cls)), key=lambda t: t[0])
    for km, r in ranked:
        if km > MAX_MATCH_KM:
            break
        if c.execute("UPDATE drivers SET available=0,status='on_ride' WHERE id=? AND available=1", (r["id"],)).rowcount == 1:
            return r, km     # atomic claim: two requests can never get the same driver
    return None, None


def release_driver(c, driver_id, lat=None, lng=None):
    if not driver_id:
        return
    if lat is not None:
        c.execute("UPDATE drivers SET available=1,status='available',lat=?,lng=? WHERE id=? AND status='on_ride'", (lat, lng, driver_id))
    else:
        c.execute("UPDATE drivers SET available=1,status='available' WHERE id=? AND status='on_ride'", (driver_id,))


def try_match(c, rid) -> bool:
    r = c.execute("SELECT * FROM rides WHERE id=?", (rid,)).fetchone()
    if not r or r["status"] != "searching":
        return False
    d, km = claim_driver(c, r["vehicle_class"], r["pickup_lat"], r["pickup_lng"])
    if not d:
        return False
    if c.execute("UPDATE rides SET driver_id=?,status='matched',matched_at=?,drv_lat=?,drv_lng=?,approach_km=? WHERE id=? AND status='searching'",
                 (d["id"], now_s(), d["lat"], d["lng"], round(km, 2), rid)).rowcount != 1:
        release_driver(c, d["id"])
        return False
    return True


# ---------------- wallet / payments / coupons ----------------
def wallet_credit(c, user_id, amount, kind, note):
    c.execute("UPDATE users SET wallet_balance=wallet_balance+? WHERE id=?", (amount, user_id))
    bal = c.execute("SELECT wallet_balance FROM users WHERE id=?", (user_id,)).fetchone()[0]
    c.execute("INSERT INTO wallet_txns(user_id,amount,kind,note,balance_after) VALUES(?,?,?,?,?)", (user_id, amount, kind, note, bal))


def wallet_debit(c, user_id, amount, kind, note):
    if c.execute("UPDATE users SET wallet_balance=wallet_balance-? WHERE id=? AND wallet_balance>=?", (amount, user_id, amount)).rowcount != 1:
        raise ApiError(402, "Insufficient wallet balance. Top up your wallet or pick another payment method.")
    bal = c.execute("SELECT wallet_balance FROM users WHERE id=?", (user_id,)).fetchone()[0]
    c.execute("INSERT INTO wallet_txns(user_id,amount,kind,note,balance_after) VALUES(?,?,?,?,?)", (user_id, -amount, kind, note, bal))


def charge(c, user_id, amount, method, ref_type, ref_id):
    """Returns (payment_status, prepaid_amount). wallet is real (ledger); upi/card are DEMO-mocked; cash/cod is collected later."""
    amount = round(amount, 2)
    prepaid, status = 0.0, "pending"
    if amount <= 0:
        status = "paid"
    elif method == "wallet":
        wallet_debit(c, user_id, amount, "payment", f"{ref_type} #{ref_id}")
        prepaid, status = amount, "paid"
    elif method in ("upi", "card"):
        prepaid, status = amount, "paid"
    c.execute("INSERT INTO payments(user_id,ref_type,ref_id,amount,method,kind,status,txn_ref) VALUES(?,?,?,?,?,'charge',?,?)",
              (user_id, ref_type, ref_id, amount, method, status, ("DEMO" if method in ("upi", "card") else method.upper()) + secrets.token_hex(4).upper()))
    return status, prepaid


def refund_to_wallet(c, user_id, amount, ref_type, ref_id, note):
    amount = round(amount, 2)
    if amount <= 0:
        return
    wallet_credit(c, user_id, amount, "refund", note)
    c.execute("INSERT INTO payments(user_id,ref_type,ref_id,amount,method,kind,status,txn_ref) VALUES(?,?,?,?,'wallet','refund','paid',?)",
              (user_id, ref_type, ref_id, amount, "RF" + secrets.token_hex(4).upper()))


def evaluate_coupon(c, user_id, code, amount, scope):
    """-> (discount, normalized_code). Raises ApiError(400) with a friendly reason."""
    code = (code or "").strip().upper()
    if not code:
        return 0.0, None
    row = c.execute("SELECT * FROM coupons WHERE code=? AND active=1", (code,)).fetchone()
    if not row:
        raise ApiError(400, "Invalid coupon code")
    if row["scope"] not in ("all", scope):
        raise ApiError(400, f"{code} is not valid for this booking type")
    if row["expires_at"] and row["expires_at"] < now_s():
        raise ApiError(400, f"{code} has expired")
    if amount < (row["min_amount"] or 0):
        raise ApiError(400, f"{code} needs a minimum of Rs {row['min_amount']:.0f}")
    if row["one_time"] and c.execute("SELECT 1 FROM coupon_uses WHERE code=? AND user_id=?", (code, user_id)).fetchone():
        raise ApiError(400, f"You have already used {code}")
    d = amount * row["value"] / 100 if row["kind"] == "percent" else row["value"]
    if row["max_discount"]:
        d = min(d, row["max_discount"])
    return round(min(d, amount - 1), 2), code


def record_coupon_use(c, code, user_id, ref_type, ref_id):
    if code:
        c.execute("INSERT INTO coupon_uses(code,user_id,ref_type,ref_id) VALUES(?,?,?,?)", (code, user_id, ref_type, ref_id))


# ---------------- trip lifecycle ----------------
def get(c, rid):
    return c.execute("SELECT * FROM rides WHERE id=?", (rid,)).fetchone()


def create_trip(c, user, kind, cls, pickup, drop, quote, payment_method, coupon, parcel=None):
    """pickup/drop = (name, lat, lng); quote = dict(fare, distance_km, eta_min, surge). Runs inside the caller's tx()."""
    scope = "parcel" if kind == "parcel" else "ride"
    discount, code = evaluate_coupon(c, user["id"], coupon, quote["fare"], scope)
    payable = round(quote["fare"] - discount, 2)
    rid = c.execute("""INSERT INTO rides(user_id,pickup,pickup_lat,pickup_lng,dropoff,drop_lat,drop_lng,distance_km,fare,eta_min,status,
                       kind,vehicle_class,otp,payment_method,discount,surge,coupon,sim,search_started_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,'searching',?,?,?,?,?,?,?,?,?)""",
                    (user["id"], pickup[0], pickup[1], pickup[2], drop[0], drop[1], drop[2], quote["distance_km"], quote["fare"], quote["eta_min"],
                     kind, cls, new_otp(), payment_method, discount, quote["surge"], code, 1 if config.DEMO_AUTOPILOT else 0, now_s())).lastrowid
    status, prepaid = charge(c, user["id"], payable, payment_method, "ride", rid)
    c.execute("UPDATE rides SET payment_status=?,paid_amount=? WHERE id=?", (status, prepaid, rid))
    record_coupon_use(c, code, user["id"], "ride", rid)
    if parcel:
        c.execute("INSERT INTO parcels(ride_id,weight_kg,size,fragile,description,recipient_name,recipient_phone,delivery_otp) VALUES(?,?,?,?,?,?,?,?)",
                  (rid, parcel["weight_kg"], parcel["size"], 1 if parcel["fragile"] else 0, parcel["description"], parcel["recipient_name"], parcel["recipient_phone"], new_otp()))
    try_match(c, rid)
    return rid


def cancel_trip(c, r, by, reason):
    if r["status"] not in ("searching", "matched", "arriving"):
        raise ApiError(409, "This trip can no longer be cancelled")
    prepaid = r["paid_amount"] or 0
    fee = CANCEL_FEE if (r["status"] == "arriving" and by == "customer" and prepaid > CANCEL_FEE) else 0.0
    refund = max(0.0, round(prepaid - fee, 2))
    c.execute("UPDATE rides SET status='cancelled',cancel_reason=?,payment_status=? WHERE id=?",
              (reason, "refunded" if prepaid > 0 else "cancelled", r["id"]))
    refund_to_wallet(c, r["user_id"], refund, "ride", r["id"], f"Refund for cancelled trip #{r['id']}")
    c.execute("DELETE FROM coupon_uses WHERE ref_type='ride' AND ref_id=?", (r["id"],))   # a cancelled booking gives the coupon back
    release_driver(c, r["driver_id"])
    return {"refund": refund, "fee": fee}


def _created_epoch(r):
    try:
        return calendar.timegm(time.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S"))
    except Exception:
        return now_s()


def expire_trip(c, r, reason):
    """Safety net for trips nobody finished (old test data, abandoned sessions): cancel, free the driver, refund what was prepaid."""
    prepaid = r["paid_amount"] or 0
    c.execute("UPDATE rides SET status='cancelled',cancel_reason=?,payment_status=? WHERE id=?", (reason, "refunded" if prepaid > 0 else "cancelled", r["id"]))
    refund_to_wallet(c, r["user_id"], prepaid, "ride", r["id"], f"Refund for expired trip #{r['id']}")
    c.execute("DELETE FROM coupon_uses WHERE ref_type='ride' AND ref_id=?", (r["id"],))
    release_driver(c, r["driver_id"])


STALE_AFTER_S = {"matched": 2 * 3600, "arriving": 2 * 3600, "started": 4 * 3600}


def complete_trip(c, r, ts=None):
    if c.execute("UPDATE rides SET status='completed',completed_at=? WHERE id=? AND status='started'", (ts or now_s(), r["id"])).rowcount != 1:
        return
    if r["payment_status"] != "paid":   # cash collected by the driver
        c.execute("UPDATE rides SET payment_status='paid' WHERE id=?", (r["id"],))
        c.execute("UPDATE payments SET status='paid' WHERE ref_type='ride' AND ref_id=? AND kind='charge'", (r["id"],))
    release_driver(c, r["driver_id"], r["drop_lat"], r["drop_lng"])


# ---------------- demo autopilot + live position ----------------
def approach_seconds(km):
    return min(45, max(8, math.ceil((km or 0) * 10)))


def trip_seconds(km):
    return min(90, max(20, math.ceil((km or 0) * 6)))


def advance(c, rid):
    """Lazy state machine, called whenever a trip is viewed: re-match while searching, time out, and (for demo/sim trips)
    move the simulated driver through arrive -> start -> complete using timestamps only (no background thread)."""
    for _ in range(6):
        r = get(c, rid)
        if not r:
            return None
        st, now = r["status"], now_s()
        if st == "searching":
            if try_match(c, rid):
                continue
            if now - (r["search_started_at"] or now) > SEARCH_TIMEOUT_S:
                cancel_trip(c, r, "system", "No driver available nearby")
            break
        limit = STALE_AFTER_S.get(st)
        if limit:
            ref = (r["started_at"] if st == "started" else None) or r["matched_at"] or r["search_started_at"] or _created_epoch(r)
            if now - ref > limit:
                expire_trip(c, r, "Trip timed out")
                break
        if not r["sim"]:
            break
        if st == "matched" and r["matched_at"] and now >= r["matched_at"] + approach_seconds(r["approach_km"]):
            c.execute("UPDATE rides SET status='arriving',arrived_at=? WHERE id=? AND status='matched'", (r["matched_at"] + approach_seconds(r["approach_km"]), rid))
            continue
        if st == "arriving" and r["arrived_at"] and now >= r["arrived_at"] + WAIT_AT_PICKUP_S:
            c.execute("UPDATE rides SET status='started',started_at=? WHERE id=? AND status='arriving'", (r["arrived_at"] + WAIT_AT_PICKUP_S, rid))
            continue
        if st == "started" and r["started_at"] and now >= r["started_at"] + trip_seconds(r["distance_km"]):
            complete_trip(c, r, r["started_at"] + trip_seconds(r["distance_km"]))
            continue
        break
    return get(c, rid)


def _lerp(a, b, f):
    return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f


def _bearing(a, b):
    y = math.sin(math.radians(b[1] - a[1])) * math.cos(math.radians(b[0]))
    x = math.cos(math.radians(a[0])) * math.sin(math.radians(b[0])) - math.sin(math.radians(a[0])) * math.cos(math.radians(b[0])) * math.cos(math.radians(b[1] - a[1]))
    return round((math.degrees(math.atan2(y, x)) + 360) % 360)


def driver_position(r, now=None):
    """-> ((lat, lng, heading) | None, phase_progress 0..1, phase)"""
    now = now or now_s()
    p, d = (r["pickup_lat"], r["pickup_lng"]), (r["drop_lat"], r["drop_lng"])
    s = (r["drv_lat"] if r["drv_lat"] is not None else p[0], r["drv_lng"] if r["drv_lng"] is not None else p[1])
    st = r["status"]
    if st == "matched" and r["matched_at"]:
        a, b, f, ph = s, p, min(1.0, max(0.0, (now - r["matched_at"]) / approach_seconds(r["approach_km"]))), "to_pickup"
    elif st == "arriving":
        a, b, f, ph = p, p, 1.0, "at_pickup"
    elif st == "started" and r["started_at"]:
        a, b, f, ph = p, d, min(1.0, max(0.0, (now - r["started_at"]) / trip_seconds(r["distance_km"]))), "on_trip"
    elif st == "completed":
        a, b, f, ph = d, d, 1.0, "done"
    else:
        return None, 0.0, st
    lat, lng = _lerp(a, b, f)
    return (round(lat, 6), round(lng, 6), _bearing(a, b) if a != b else 0), f, ph


def snapshot(c, r, viewer):
    """Everything the tracking screen needs. OTPs are only revealed to the customer who owns the trip."""
    now = now_s()
    pos, f, phase = driver_position(r, now)
    sp = SPEED_KMH.get(r["vehicle_class"], 26)
    st = r["status"]
    if st == "matched":
        eta = max(1, math.ceil((r["approach_km"] or 0) / sp * 60 * (1 - f)))
    elif st == "started":
        eta = max(0, math.ceil((r["eta_min"] or 0) * (1 - f)))
    else:
        eta = 0 if st in ("arriving", "completed") else (r["eta_min"] or 0)
    drv = None
    if r["driver_id"]:
        d = c.execute("""SELECT d.id,u.name,u.phone,v.plate,v.type vtype,d.capacity_rating rating FROM drivers d JOIN users u ON u.id=d.user_id
                         LEFT JOIN vehicles v ON v.id=d.vehicle_id WHERE d.id=?""", (r["driver_id"],)).fetchone()
        if d:
            drv = {"id": d["id"], "name": d["name"], "phone": d["phone"], "plate": d["plate"], "vehicle_type": d["vtype"], "rating": d["rating"],
                   "lat": pos[0] if pos else None, "lng": pos[1] if pos else None, "heading": pos[2] if pos else 0}
    owner = viewer["role"] == "customer" and viewer["id"] == r["user_id"]
    parcel = c.execute("SELECT * FROM parcels WHERE ride_id=?", (r["id"],)).fetchone() if r["kind"] == "parcel" else None
    timeline = [{"status": "booked", "at": calendar.timegm(time.strptime(r["created_at"], "%Y-%m-%d %H:%M:%S")) if r["created_at"] else None}]
    for key, label in (("matched_at", "matched"), ("arrived_at", "arriving"), ("started_at", "started"), ("completed_at", "completed")):
        if r[key]:
            timeline.append({"status": label, "at": r[key]})
    out = {
        "id": r["id"], "kind": r["kind"], "status": st, "phase": phase, "vehicle_class": r["vehicle_class"],
        "pickup": {"name": r["pickup"], "lat": r["pickup_lat"], "lng": r["pickup_lng"]},
        "drop": {"name": r["dropoff"], "lat": r["drop_lat"], "lng": r["drop_lng"]},
        "distance_km": r["distance_km"], "fare": r["fare"], "discount": r["discount"] or 0, "payable": round(r["fare"] - (r["discount"] or 0), 2),
        "surge": r["surge"], "payment_method": r["payment_method"], "payment_status": r["payment_status"], "coupon": r["coupon"],
        "eta_min": eta, "progress": round(f, 3), "driver": drv,
        "approach_from": {"lat": r["drv_lat"], "lng": r["drv_lng"]} if r["drv_lat"] is not None else None, "timeline": timeline, "rating": r["rating"], "review": r["review"],
        "cancel_reason": r["cancel_reason"], "can_cancel": st in ("searching", "matched", "arriving"), "demo": bool(r["sim"]),
        "otp": r["otp"] if owner and st in ("matched", "arriving") else None,
    }
    if parcel:
        out["parcel"] = {"weight_kg": parcel["weight_kg"], "size": parcel["size"], "fragile": bool(parcel["fragile"]), "description": parcel["description"],
                         "recipient_name": parcel["recipient_name"], "recipient_phone": parcel["recipient_phone"]}
        out["delivery_otp"] = parcel["delivery_otp"] if owner and st in ("matched", "arriving", "started") else None
    if viewer["role"] == "driver":
        cu = c.execute("SELECT name,phone FROM users WHERE id=?", (r["user_id"],)).fetchone()
        out["customer"] = {"name": cu["name"], "phone": cu["phone"]} if cu else None
        out["driver_earning"] = round(r["fare"] * DRIVER_SHARE, 2)
    return out


def strip_private(row: dict, viewer) -> dict:
    owner = viewer["role"] == "customer" and viewer["id"] == row.get("user_id")
    if not owner:
        row.pop("otp", None)
        row.pop("delivery_otp", None)
    return row
