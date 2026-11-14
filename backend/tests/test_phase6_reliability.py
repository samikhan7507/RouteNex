"""Money safety: two requests that cancel/expire the same trip at the same moment must refund exactly once."""
import threading
import db
from services import trips
from services.errors import ApiError


def make_paid_ride(sql, status="searching"):
    sql("UPDATE users SET wallet_balance=400 WHERE id=1")                       # 500 topped up, 100 paid for the ride
    sql("""INSERT INTO rides(user_id,pickup,pickup_lat,pickup_lng,dropoff,drop_lat,drop_lng,distance_km,fare,eta_min,status,kind,vehicle_class,otp,
           payment_method,payment_status,paid_amount,search_started_at) VALUES(1,'A',26.9,75.8,'B',26.8,75.8,5,100,10,?, 'ride','cab','1234','wallet','paid',100,0)""", (status,))
    return sql("SELECT id FROM rides ORDER BY id DESC LIMIT 1")[0][0]


def race(action, rid):
    """Run `action(conn, ride_row)` in two threads that both read the trip BEFORE either one writes (the worst case)."""
    barrier, out = threading.Barrier(2), []

    def worker():
        try:
            with db.tx() as c:
                r = trips.get(c, rid)
                barrier.wait(timeout=5)
                out.append(action(c, r))
        except ApiError as e:
            out.append(e.status)
    ts = [threading.Thread(target=worker) for _ in range(2)]
    [t.start() for t in ts]; [t.join() for t in ts]
    return out


def test_simultaneous_cancel_refunds_once(sql):
    rid = make_paid_ride(sql)
    out = race(lambda c, r: trips.cancel_trip(c, r, "customer", "race"), rid)
    assert sorted(map(str, out)) == sorted(["409", str({"refund": 100.0, "fee": 0.0})]), out
    assert sql("SELECT wallet_balance FROM users WHERE id=1")[0][0] == 500.0
    assert sql("SELECT COUNT(*) FROM payments WHERE kind='refund' AND ref_id=?", (rid,))[0][0] == 1


def test_simultaneous_expiry_refunds_once(sql):
    rid = make_paid_ride(sql, "matched")
    race(lambda c, r: trips.expire_trip(c, r, "Trip timed out"), rid)
    assert sql("SELECT wallet_balance FROM users WHERE id=1")[0][0] == 500.0
    assert sql("SELECT COUNT(*) FROM payments WHERE kind='refund' AND ref_id=?", (rid,))[0][0] == 1


def test_cancel_after_cancel_is_rejected_and_never_refunds_again(sql):
    rid = make_paid_ride(sql)
    with db.tx() as c:
        trips.cancel_trip(c, trips.get(c, rid), "customer", "once")
    try:
        with db.tx() as c:
            trips.cancel_trip(c, trips.get(c, rid), "customer", "twice")
        assert False, "second cancel must fail"
    except ApiError as e:
        assert e.status == 409
    assert sql("SELECT wallet_balance FROM users WHERE id=1")[0][0] == 500.0
