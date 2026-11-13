#!/usr/bin/env python3
"""Idempotent bootstrap. NEVER deletes operational data.

python scripts/bootstrap.py                  # admin only (production-safe)
python scripts/bootstrap.py --catalog        # admin + append-only starter catalogue
python scripts/bootstrap.py --demo           # local/demo data; refuses production
python scripts/bootstrap.py --rotate-admin-password  # explicit password rotation from ADMIN_PASSWORD
"""
from __future__ import annotations
import argparse
import hashlib
from datetime import timedelta
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import func, select
from app.core.config import get_settings
from app.core.security import hash_password, protect_code
from app.db import session_scope
from app.models import (Address, Alert, Coupon, Driver, DriverEarning, Order, OrderItem, Product, Trip, User, Vehicle, utcnow)
from app.services import catalog, payments
from app.services.pricing import IST


def ensure_admin(db, rotate=False):
    s = get_settings()
    email = s.admin_email.lower()
    password = s.admin_password or ("sami@123" if not s.is_production else "")
    if not password:
        raise SystemExit("ADMIN_PASSWORD is required")
    admin = db.scalar(select(User).where(User.email == email))
    if not admin:
        admin = User(name=s.admin_name, email=email, password_hash=hash_password(password), role="admin")
        db.add(admin)
        db.flush()
        print(f"Created administrator {email}")
    elif rotate:
        admin.password_hash = hash_password(password)
        print(f"Rotated administrator password for {email}")
    else:
        print(f"Administrator {email} already exists; password left unchanged")
    return admin


def seed_demo(db):
    s = get_settings()
    if s.is_production or not s.demo_mode:
        raise SystemExit("Demo seeding is refused outside an explicitly configured development/demo environment")
    demo_hash = hash_password("Demo@123")
    people = [("Aarav Sharma", "customer@routenex.in", "+919876543210", "customer"),
              ("Diya Rathore", "driver@routenex.in", "+919000000002", "driver"),
              ("Kabir Mehta", "dispatcher@routenex.in", "+919000000003", "dispatcher"),
              ("Meera Joshi", "fleet@routenex.in", "+919000000004", "fleet_manager")]
    for i in range(2, 13):
        people.append((f"Driver {i:02d}", f"driver{i}@routenex.in", f"+9190000001{i:02d}", "driver"))
    users = {}
    for name, email, phone, role in people:
        user = db.scalar(select(User).where(User.email == email))
        if not user:
            user = User(name=name, email=email, phone=phone, password_hash=demo_hash, role=role,
                        wallet_balance_paise=50000 if role == "customer" else 0)
            db.add(user)
            db.flush()
        users[email] = user
    customer = users["customer@routenex.in"]
    locations = [("C-Scheme", 26.9124, 75.7873, "302001"), ("Malviya Nagar", 26.8540, 75.8243, "302017"),
                 ("Vaishali Nagar", 26.9126, 75.7442, "302021"), ("Mansarovar", 26.8505, 75.7628, "302020"),
                 ("Jagatpura", 26.8399, 75.8322, "302017"), ("Raja Park", 26.8942, 75.8210, "302004")]
    addresses = []
    for i, (name, lat, lng, pin) in enumerate(locations):
        a = db.scalar(select(Address).where(Address.user_id == customer.id, Address.label == name))
        if not a:
            a = Address(user_id=customer.id, label=name, line1=f"{12+i}, {name} Main Road", city="Jaipur", state="Rajasthan", pincode=pin, lat=lat, lng=lng)
            db.add(a)
            db.flush()
        addresses.append(a)
    fleet = [("RJ14-RN-101", "Bike", 20, 400), ("RJ14-RN-102", "Bike", 25, 420),
             ("RJ14-RN-201", "Electric Cargo", 350, 700), ("RJ14-RN-202", "Mini Van", 650, 1200),
             ("RJ14-RN-203", "Van", 900, 1400), ("RJ14-RN-301", "Pickup", 1200, 1700),
             ("RJ14-RN-302", "Pickup", 1500, 1800), ("RJ14-RN-401", "Reefer Van", 800, 2000),
             ("RJ14-RN-501", "Truck", 3500, 2600), ("RJ14-RN-502", "Truck", 5000, 3100),
             ("RJ14-RN-601", "EV Van", 700, 800), ("RJ14-RN-701", "Auto", 120, 900)]
    vehicles = []
    for i, (plate, typ, cap, cost) in enumerate(fleet):
        v = db.scalar(select(Vehicle).where(Vehicle.plate == plate))
        if not v:
            loc = locations[(i + 2) % len(locations)]
            v = Vehicle(plate=plate, type=typ, capacity_kg=cap, cost_per_km_paise=cost, status="available", lat=loc[1], lng=loc[2], documents="Verified")
            db.add(v)
            db.flush()
        vehicles.append(v)
    driver_users = [u for u in users.values() if u.role == "driver"]
    drivers = []
    for i, u in enumerate(driver_users[:12]):
        d = db.scalar(select(Driver).where(Driver.user_id == u.id))
        if not d:
            loc = locations[i % len(locations)]
            d = Driver(user_id=u.id, vehicle_id=vehicles[i].id, license_number=f"RJ14-202{i}-00{i+11:02d}", documents="Verified",
                       service="both", online=True, status="available", lat=loc[1] + 0.002, lng=loc[2] - 0.002)
            db.add(d)
            db.flush()
        drivers.append(d)
    catalog.sync(db)
    offers = [("WELCOME50", "50% off your first booking, up to ₹75", "all", "percent", 50, 7500, 10000, True),
              ("RIDE20", "20% off rides, up to ₹60", "ride", "percent", 20, 6000, 8000, False),
              ("PARCEL25", "₹25 off parcels above ₹120", "parcel", "flat", 2500, None, 12000, False),
              ("SHOP100", "₹100 off shop orders above ₹799", "shop", "flat", 10000, None, 79900, False)]
    for code, title, scope, kind, value, cap, minimum, once in offers:
        if not db.scalar(select(Coupon.id).where(Coupon.code == code)):
            db.add(Coupon(code=code, title=title, scope=scope, kind=kind, value=value, max_discount_paise=cap, min_amount_paise=minimum, one_time=once))
    if db.scalar(select(func.count(Order.id))) == 0:
        products = list(db.scalars(select(Product).order_by(Product.id).limit(12)))
        today = utcnow().astimezone(IST).replace(hour=8, minute=0, second=0, microsecond=0)
        end = today.replace(hour=23, minute=59, second=59)
        for i in range(8):
            p, a, qty = products[i % len(products)], addresses[i % len(addresses)], 1 + i % 3
            p.stock -= qty
            subtotal = p.price_paise * qty
            fee = 0 if subtotal >= 49900 else 3900
            code = f"{(i * 137 + 421) % 1_000_000:06d}"
            o = Order(user_id=customer.id, address_id=a.id, status="placed", subtotal_paise=subtotal, delivery_fee_paise=fee,
                      total_paise=subtotal + fee, payment_method="cod", payment_status="pending", priority=1 + i % 5,
                      delivery_window_start=today, delivery_window_end=end, weight_grams=p.weight_grams * qty,
                      delivery_otp_hash=hashlib.sha256(code.encode()).hexdigest(), delivery_otp_encrypted=protect_code(code),
                      idempotency_key=f"demo-order-{i}")
            db.add(o)
            db.flush()
            db.add(OrderItem(order_id=o.id, product_id=p.id, product_name=p.name, sku=p.sku, unit_price_paise=p.price_paise, quantity=qty, weight_grams=p.weight_grams))
            payments.instant_payment(db, customer, "order", o, "cod")
            if i >= 6:
                o.status = "delivered"
                payments.settle_cash(db, "order", o)
    if db.scalar(select(func.count(Trip.id))) == 0:
        from app.services.trips import new_code, code_hash
        for i in range(3):
            pickup, drop = locations[i], locations[(i + 3) % len(locations)]
            pc, dc = new_code(), new_code()
            t = Trip(user_id=customer.id, driver_id=drivers[i].id if i < 2 else None, kind="ride", vehicle_class="cab",
                     status="completed" if i < 2 else "searching", pickup_name=pickup[0], pickup_lat=pickup[1], pickup_lng=pickup[2],
                     drop_name=drop[0], drop_lat=drop[1], drop_lng=drop[2], distance_km=6.5 + i, fare_paise=15000 + i * 2000,
                     total_paise=15000 + i * 2000, eta_min=22, payment_method="cash", payment_status="paid" if i < 2 else "pending",
                     pickup_otp_hash=code_hash(pc), pickup_otp_encrypted=protect_code(pc), delivery_otp_hash=code_hash(dc), delivery_otp_encrypted=protect_code(dc),
                     simulated=True, idempotency_key=f"demo-trip-{i}", completed_at=utcnow() - timedelta(days=i) if i < 2 else None)
            db.add(t)
            db.flush()
            payments.instant_payment(db, customer, "trip", t, "cash")
            if i < 2:
                payments.settle_cash(db, "trip", t)
                net = t.total_paise * 80 // 100
                db.add(DriverEarning(driver_id=t.driver_id, trip_id=t.id, gross_paise=t.total_paise, platform_fee_paise=t.total_paise-net, net_paise=net))
    if db.scalar(select(func.count(Alert.id))) == 0:
        db.add_all([Alert(type="maintenance", severity="low", message="Preventive service due for RJ14-RN-502", entity_type="vehicle", entity_id=vehicles[9].id),
                    Alert(type="capacity", severity="medium", message="Review evening demand in Sitapura before assigning vans", entity_type="network")])
    db.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument("--catalog", action="store_true")
    parser.add_argument("--rotate-admin-password", action="store_true")
    args = parser.parse_args()
    with session_scope() as db:
        ensure_admin(db, rotate=args.rotate_admin_password)
        if args.catalog or args.demo:
            added = catalog.sync(db)
            print(f"Catalogue sync: {added} new products; existing products untouched")
        if args.demo:
            seed_demo(db)
            print("Demo data ready. Existing operational rows were not deleted.")
    print("Bootstrap complete.")


if __name__ == "__main__":
    main()
