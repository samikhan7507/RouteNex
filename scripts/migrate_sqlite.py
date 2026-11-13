#!/usr/bin/env python3
"""One-way, transactional SQLite (v2) -> PostgreSQL (v3) data migration.

The source is opened READ-ONLY. The target must already be at Alembic head and
must be empty (run BEFORE scripts/bootstrap.py). Dry-run is the default:

    python scripts/migrate_sqlite.py --source /path/to/legacy-routenex.db
    python scripts/migrate_sqlite.py --source /path/to/legacy-routenex.db --apply

Money is converted from REAL rupees to integer paise. Legacy plaintext handover
OTPs are rotated to new 6-digit encrypted codes. Ambiguous delivery windows are
normalised to timezone-aware IST windows and reported. Nothing is deleted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import secrets
import sqlite3
import sys
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import create_engine, func, select, text
from app.core.config import get_settings
from app.core.security import protect_code
from app.models import (Address, Alert, AssistantAction, AuditLog, Coupon, CouponUse, Driver,
                        DriverEarning, Maintenance, Notification, Order, OrderItem, Payment,
                        Product, Refund, Route, RouteStop, Trip, User, Vehicle, WalletTransaction)
from app.services.catalog import photo_for
from app.services.pricing import IST

HEAD = "0002"
SERIAL_MODELS = [User, Address, Product, Coupon, CouponUse, Order, OrderItem, Vehicle, Driver,
                 Trip, Route, Payment, Refund, WalletTransaction, Alert, Notification, AuditLog,
                 Maintenance, DriverEarning, AssistantAction]
EMPTY_CHECK = SERIAL_MODELS + [RouteStop]


class MigrationError(Exception):
    pass


def paise(value) -> int:
    if value is None:
        return 0
    return int((Decimal(str(value)) * 100).to_integral_value(rounding=ROUND_HALF_UP))


def parse_ts(value):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    s = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(s, fmt)
                break
            except ValueError:
                continue
        else:
            raise MigrationError(f"Unparseable timestamp: {value!r}")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)  # SQLite CURRENT_TIMESTAMP is UTC
    return dt


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:120] or "item"


def delivery_window(raw, created: datetime, report):
    base = (created or datetime.now(timezone.utc)).astimezone(IST).date()
    m = re.search(r"(today|tomorrow)?\s*(\d{1,2}):(\d{2})", str(raw or ""), re.I)
    if m:
        day = base + timedelta(days=1 if (m.group(1) or "").lower() == "tomorrow" else 0)
        hour, minute = min(23, int(m.group(2))), min(59, int(m.group(3)))
        start = datetime.combine(day, time(0, 0), IST)
        end = datetime.combine(day, time(hour, minute), IST)
        if end <= start:
            end = datetime.combine(day, time(23, 59), IST)
        return start, end
    report["assumptions"]["delivery_windows_defaulted"] += 1
    return datetime.combine(base, time(9, 0), IST), datetime.combine(base, time(18, 0), IST)


def new_code():
    return f"{secrets.randbelow(1_000_000):06d}"


def code_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def read_source(path: Path):
    if not path.exists():
        raise MigrationError(f"Source database not found: {path}")
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def rows(table):
        if table not in tables:
            return []
        order = "id" if any(r[1] == "id" for r in conn.execute(f"PRAGMA table_info({table})")) else "rowid"
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY {order}")]

    data = {t: rows(t) for t in ("users", "addresses", "items", "coupons", "coupon_uses", "vehicles",
                                 "drivers", "routes", "orders", "order_items", "route_orders", "rides",
                                 "parcels", "payments", "wallet_txns", "alerts", "notifications",
                                 "audit_logs", "maintenance", "assistant_actions", "otp_codes")}
    conn.close()
    return data


def build(data, report):
    out = {}
    errors = report["errors"]
    users = {r["id"]: r for r in data["users"]}
    for u in data["users"]:
        email = (u.get("email") or "").strip().lower() or None
        phone = (u.get("phone") or "").strip() or None
        if not email and not phone:
            errors.append(f"user {u['id']} has neither email nor phone")
        created = parse_ts(u.get("created_at")) or datetime.now(timezone.utc)
        out.setdefault("users", []).append(dict(id=u["id"], name=u["name"], email=email, phone=phone,
            password_hash=u.get("password_hash"), role=u["role"], active=bool(u.get("active", 1)),
            wallet_balance_paise=max(0, paise(u.get("wallet_balance"))), created_at=created, updated_at=created))

    for a in data["addresses"]:
        if a.get("lat") is None or a.get("lng") is None:
            report["assumptions"]["address_coordinates_defaulted"] += 1
        out.setdefault("addresses", []).append(dict(id=a["id"], user_id=a["user_id"], label=a.get("label") or "Home",
            line1=a.get("line1") or "Address not recorded", city=a.get("city") or "Jaipur",
            state=a.get("state") or "Rajasthan", pincode=(a.get("pincode") or "302001")[:6],
            lat=a.get("lat") if a.get("lat") is not None else 26.9124,
            lng=a.get("lng") if a.get("lng") is not None else 75.7873))

    products = {}
    for it in data["items"]:
        price = paise(it.get("price"))
        if price <= 0:
            errors.append(f"item {it['id']} has non-positive price")
            continue
        if not it.get("name"):
            errors.append(f"item {it['id']} has no name")
            continue
        kg = it.get("weight_kg")
        row = dict(id=it["id"], sku=f"LEGACY-{it['id']:05d}", slug=f"legacy-{it['id']}-{slugify(it['name'])}",
            name=it["name"], description=it.get("description") or "", category=it.get("category") or "General",
            brand="RouteNex Essentials", unit="1 pack", price_paise=price, compare_at_paise=None,
            stock=max(0, int(it.get("stock") or 0)), reserved=0,
            weight_grams=max(1, int((kg if kg is not None else 0.1) * 1000)),
            image_path=f"/products/{photo_for(it.get('category') or 'General', it['name'])}.jpg",
            image_credit="Pexels · illustrative category photo", rating=4.5, review_count=0,
            active=bool(it.get("active", 1)))
        products[it["id"]] = row
        out.setdefault("products", []).append(row)

    for c in data["coupons"]:
        kind = c.get("kind") or "percent"
        out.setdefault("coupons", []).append(dict(code=c["code"].upper(), title=c.get("title") or c["code"],
            scope=c.get("scope") or "all", kind=kind,
            value=int(round(c.get("value") or 0)) if kind == "percent" else paise(c.get("value")),
            max_discount_paise=paise(c["max_discount"]) if c.get("max_discount") else None,
            min_amount_paise=paise(c.get("min_amount")), one_time=bool(c.get("one_time")),
            active=bool(c.get("active", 1)), expires_at=parse_ts(c.get("expires_at"))))
    coupon_codes = {c["code"] for c in out.get("coupons", [])}

    for v in data["vehicles"]:
        out.setdefault("vehicles", []).append(dict(id=v["id"], plate=v["plate"], type=v["type"],
            capacity_kg=v.get("capacity_kg") or 1, cost_per_km_paise=paise(v.get("cost_per_km") or 10),
            status=v.get("status") or "available", lat=v.get("lat"), lng=v.get("lng"),
            documents=v.get("documents") or "Pending verification", next_maintenance=parse_ts(v.get("next_maintenance"))))

    for d in data["drivers"]:
        rating = min(5.0, max(0.0, float(d.get("capacity_rating") or 5.0)))
        out.setdefault("drivers", []).append(dict(id=d["id"], user_id=d["user_id"], vehicle_id=d.get("vehicle_id"),
            license_number=d.get("license") or f"LEGACY-{d['id']}", documents=d.get("documents") or "Pending verification",
            service=d.get("service") or "both", online=bool(d.get("online", d.get("available", 1))),
            status=d.get("status") or "available", lat=d.get("lat"), lng=d.get("lng"),
            rating=round(rating, 1), rating_count=int(d.get("rating_count") or 0)))

    route_status = {"planned": "planned", "active": "active", "completed": "completed", "done": "completed",
                    "cancelled": "cancelled", "reroute_required": "reroute_required"}
    active_vehicle, active_driver = set(), set()
    route_ids = set()
    for r in data["routes"]:
        status = route_status.get(r.get("status") or "planned")
        if not status:
            errors.append(f"route {r['id']} has unknown status {r.get('status')!r}")
            continue
        if not r.get("vehicle_id") or not r.get("driver_id"):
            errors.append(f"route {r['id']} is missing vehicle/driver and cannot be imported")
            continue
        if status in ("planned", "active"):
            if r["vehicle_id"] in active_vehicle or r["driver_id"] in active_driver:
                errors.append(f"route {r['id']} double-books an active vehicle/driver; resolve in v2 before migrating")
                continue
            active_vehicle.add(r["vehicle_id"]); active_driver.add(r["driver_id"])
        try:
            geometry = json.loads(r.get("geometry") or "[]")
        except (TypeError, ValueError):
            geometry = []
        route_ids.add(r["id"])
        out.setdefault("routes", []).append(dict(id=r["id"], plan_id=None, vehicle_id=r["vehicle_id"],
            driver_id=r["driver_id"], status=status, distance_km=r.get("distance_km") or 0,
            duration_min=int(r.get("duration_min") or 0), cost_paise=paise(r.get("cost")),
            load_kg=r.get("load_kg") or 0, geometry=geometry if isinstance(geometry, list) else [],
            reason=(r.get("reason") or "")[:240], created_at=parse_ts(r.get("created_at")) or datetime.now(timezone.utc)))

    order_status = {"awaiting_payment": "awaiting_payment", "placed": "placed", "assigned": "assigned",
                    "picked_up": "picked_up", "out_for_delivery": "out_for_delivery", "delivered": "delivered",
                    "cancelled": "cancelled", "failed": "failed"}
    pay_method = {"cod": "cod", "cash": "cod", "wallet": "wallet", "upi": "razorpay", "card": "razorpay", "razorpay": "razorpay"}
    order_ids = set()
    for o in data["orders"]:
        status = order_status.get(o.get("status") or "placed")
        if not status:
            errors.append(f"order {o['id']} has unknown status {o.get('status')!r}")
            continue
        created = parse_ts(o.get("created_at")) or datetime.now(timezone.utc)
        start, end = delivery_window(o.get("delivery_window"), created, report)
        discount = paise(o.get("discount"))
        total = paise(o.get("total"))
        method = pay_method.get(o.get("payment_method") or "cod")
        if not method:
            errors.append(f"order {o['id']} has unknown payment method {o.get('payment_method')!r}")
            continue
        route_id = o.get("route_id") if o.get("route_id") in route_ids else None
        if o.get("route_id") and route_id is None:
            report["assumptions"]["order_route_links_dropped"] += 1
        order_ids.add(o["id"])
        out.setdefault("orders", []).append(dict(id=o["id"], user_id=o["user_id"], address_id=o["address_id"],
            status=status, subtotal_paise=total + discount, discount_paise=discount, delivery_fee_paise=0,
            total_paise=total, coupon_code=(o.get("coupon") or None), payment_method=method,
            payment_status=o.get("payment_status") or "pending", priority=min(5, max(1, int(o.get("priority") or 1))),
            delivery_window_start=start, delivery_window_end=end, weight_grams=max(0, int((o.get("weight_kg") or 0) * 1000)),
            idempotency_key=f"legacy-order-{o['id']}", route_id=route_id,
            created_at=created, updated_at=parse_ts(o.get("updated_at")) or created))

    for li in data["order_items"]:
        p = products.get(li["item_id"])
        if not p:
            errors.append(f"order_item {li.get('id')} references missing item {li['item_id']}")
            continue
        if li["order_id"] not in order_ids:
            continue
        out.setdefault("order_items", []).append(dict(id=li["id"], order_id=li["order_id"], product_id=p["id"],
            product_name=p["name"], sku=p["sku"], unit_price_paise=paise(li.get("unit_price")),
            quantity=int(li.get("quantity") or 1), weight_grams=p["weight_grams"]))

    seen_stop_order = set()
    seq_by_route = {}
    for s in sorted(data["route_orders"], key=lambda x: (x["route_id"], x.get("stop_sequence") or 0)):
        if s["route_id"] not in route_ids or s["order_id"] not in order_ids:
            continue
        if s["order_id"] in seen_stop_order:
            errors.append(f"order {s['order_id']} appears in multiple routes")
            continue
        seen_stop_order.add(s["order_id"])
        seq_by_route[s["route_id"]] = seq_by_route.get(s["route_id"], 0) + 1
        out.setdefault("route_stops", []).append(dict(route_id=s["route_id"], order_id=s["order_id"],
            sequence=seq_by_route[s["route_id"]], eta=(s.get("eta") or "")[:12],
            arrival_min=int(s.get("arrival_min") or 0), delay_risk=s.get("delay_risk")))

    parcels = {p["ride_id"]: p for p in data["parcels"]}
    trip_status = {"awaiting_payment": "awaiting_payment", "searching": "searching", "matched": "matched",
                   "arriving": "arrived", "arrived": "arrived", "started": "started", "completed": "completed",
                   "cancelled": "cancelled", "expired": "expired"}
    trip_pay_method = {"cash": "cash", "wallet": "wallet", "upi": "razorpay", "card": "razorpay", "razorpay": "razorpay"}
    active_trip_driver = set()
    for r in data["rides"]:
        status = trip_status.get(r.get("status") or "searching")
        if not status:
            errors.append(f"ride {r['id']} has unknown status {r.get('status')!r}")
            continue
        kind = r.get("kind") or ("parcel" if r["id"] in parcels else "ride")
        p = parcels.get(r["id"], {})
        weight = p.get("weight_kg")
        cls = r.get("vehicle_class")
        if not cls:
            cls = ("pbike" if (weight or 0) <= 10 else "pmini" if (weight or 0) <= 150 else "pvan") if kind == "parcel" else "cab"
        method = trip_pay_method.get(r.get("payment_method") or "cash")
        if not method:
            errors.append(f"ride {r['id']} has unknown payment method {r.get('payment_method')!r}")
            continue
        if status in ("matched", "arrived", "started") and r.get("driver_id"):
            if r["driver_id"] in active_trip_driver:
                errors.append(f"ride {r['id']} double-books active driver {r['driver_id']}; resolve in v2 first")
                continue
            active_trip_driver.add(r["driver_id"])
        created = parse_ts(r.get("created_at")) or datetime.now(timezone.utc)
        pc, dc = new_code(), new_code()
        report["assumptions"]["handover_otps_rotated"] += 1
        fare = paise(r.get("fare"))
        discount = paise(r.get("discount"))
        out.setdefault("trips", []).append(dict(id=r["id"], user_id=r["user_id"], driver_id=r.get("driver_id"),
            kind=kind, vehicle_class=cls, status=status, pickup_name=r.get("pickup") or "Pickup",
            pickup_lat=r.get("pickup_lat") or 26.9124, pickup_lng=r.get("pickup_lng") or 75.7873,
            drop_name=r.get("dropoff") or "Drop-off", drop_lat=r.get("drop_lat") or 26.9124, drop_lng=r.get("drop_lng") or 75.7873,
            distance_km=r.get("distance_km") or 0, fare_paise=fare, discount_paise=discount,
            total_paise=max(0, fare - discount), eta_min=int(r.get("eta_min") or 0), eta_source="legacy",
            payment_method=method, payment_status=r.get("payment_status") or "pending", coupon_code=r.get("coupon"),
            pickup_otp_hash=code_hash(pc), pickup_otp_encrypted=protect_code(pc),
            delivery_otp_hash=code_hash(dc) if kind == "parcel" else None,
            delivery_otp_encrypted=protect_code(dc) if kind == "parcel" else None,
            recipient_name=p.get("recipient_name"), recipient_phone=p.get("recipient_phone"),
            weight_kg=weight, parcel_size=p.get("size"), fragile=bool(p.get("fragile")),
            description=p.get("description"), simulated=bool(r.get("sim")),
            idempotency_key=f"legacy-trip-{r['id']}", search_started_at=parse_ts(r.get("search_started_at")) or created,
            matched_at=parse_ts(r.get("matched_at")), arrived_at=parse_ts(r.get("arrived_at")),
            started_at=parse_ts(r.get("started_at")), completed_at=parse_ts(r.get("completed_at")),
            cancelled_at=created if status == "cancelled" else None, cancel_reason=r.get("cancel_reason"),
            rating=r.get("rating"), review=r.get("review"), created_at=created, updated_at=created))

    charge_by_ref = {}
    for p in data["payments"]:
        if p.get("kind") == "charge":
            charge_by_ref[(p["user_id"], p.get("ref_type"), p.get("ref_id"))] = p["id"]
    seen_txn = set()
    payment_status = {"paid": "captured", "pending": "created", "created": "created", "failed": "failed",
                      "refunded": "refunded", "cancelled": "failed"}
    purpose_map = {"order": "order", "ride": "trip", "trip": "trip", "wallet": "wallet_topup", "wallet_topup": "wallet_topup"}
    for p in data["payments"]:
        amount = paise(p.get("amount"))
        if amount <= 0:
            report["skipped"]["zero_amount_payments"] += 1
            continue
        purpose = purpose_map.get(p.get("ref_type"))
        if not purpose:
            errors.append(f"payment {p['id']} has unknown ref_type {p.get('ref_type')!r}")
            continue
        method = (p.get("method") or "").lower()
        provider = "wallet" if method == "wallet" else "cash" if method in ("cash", "cod") else "demo"
        status = payment_status.get(p.get("status") or "pending")
        if not status:
            errors.append(f"payment {p['id']} has unknown status {p.get('status')!r}")
            continue
        if p.get("kind") == "refund":
            status = "refunded"
        created = parse_ts(p.get("created_at")) or datetime.now(timezone.utc)
        txn = p.get("txn_ref")
        if txn in seen_txn:
            txn = None
        if txn:
            seen_txn.add(txn)
        out.setdefault("payments", []).append(dict(id=p["id"], public_id=f"legacy-pay-{p['id']}", user_id=p["user_id"],
            purpose=purpose, reference_id=p.get("ref_id"), provider=provider, provider_order_id=None,
            provider_payment_id=txn, amount_paise=amount, currency="INR", status=status, method=method[:20],
            idempotency_key=f"legacy-payment-{p['id']}", receipt=f"legacy-{p['id']}", failure_reason="",
            created_at=created, updated_at=created, captured_at=created if status in ("captured", "refunded") else None))
        if p.get("kind") == "refund":
            original = charge_by_ref.get((p["user_id"], p.get("ref_type"), p.get("ref_id")), p["id"])
            out.setdefault("refunds", []).append(dict(payment_id=original, provider_refund_id=None,
                amount_paise=amount, status="processed", reason="Imported legacy wallet refund",
                created_at=created, processed_at=created))

    for w in data["wallet_txns"]:
        out.setdefault("wallet_transactions", []).append(dict(id=w["id"], user_id=w["user_id"], payment_id=None,
            amount_paise=paise(w.get("amount")), kind=(w.get("kind") or "adjustment")[:20],
            balance_after_paise=paise(w.get("balance_after")), note=(w.get("note") or "")[:240],
            created_at=parse_ts(w.get("created_at")) or datetime.now(timezone.utc)))

    for a in data["alerts"]:
        out.setdefault("alerts", []).append(dict(id=a["id"], type=a.get("type") or "general",
            severity=a.get("severity") or "medium", message=(a.get("message") or "")[:500],
            entity_type=a.get("entity_type") or "", entity_id=a.get("entity_id"),
            acknowledged=bool(a.get("acknowledged")), created_at=parse_ts(a.get("created_at")) or datetime.now(timezone.utc)))

    for n in data["notifications"]:
        out.setdefault("notifications", []).append(dict(id=n["id"], user_id=n["user_id"], title=(n.get("title") or "")[:160],
            body=(n.get("message") or "")[:1000], read=bool(n.get("read")),
            created_at=parse_ts(n.get("created_at")) or datetime.now(timezone.utc)))

    for a in data["audit_logs"]:
        details = a.get("details")
        try:
            details = json.loads(details) if details else {}
            if not isinstance(details, dict):
                details = {"legacy": details}
        except (TypeError, ValueError):
            details = {"legacy": str(details)}
        actor = a.get("user_id") if a.get("user_id") in users else None
        out.setdefault("audit_logs", []).append(dict(id=a["id"], actor_id=actor, action=(a.get("action") or "")[:60],
            entity=(a.get("entity") or "")[:40], entity_id=str(a.get("entity_id") or "")[:60], details=details,
            ip_address="", request_id="", created_at=parse_ts(a.get("created_at")) or datetime.now(timezone.utc)))

    for m in data["maintenance"]:
        scheduled = parse_ts(m.get("scheduled_for")) or datetime.now(timezone.utc)
        out.setdefault("maintenance_records", []).append(dict(id=m["id"], vehicle_id=m["vehicle_id"],
            description=(m.get("description") or "")[:500], scheduled_for=scheduled,
            status=m.get("status") or "scheduled", cost_paise=paise(m.get("cost")), created_at=scheduled))

    seen_coupon_ref = set()
    for cu in data["coupon_uses"]:
        code = (cu.get("code") or "").upper()
        ref_type = "trip" if cu.get("ref_type") == "ride" else cu.get("ref_type")
        if code not in coupon_codes or ref_type not in ("order", "trip"):
            report["skipped"]["orphan_coupon_uses"] += 1
            continue
        key = (ref_type, cu.get("ref_id"))
        if key in seen_coupon_ref:
            report["skipped"]["duplicate_coupon_uses"] += 1
            continue
        seen_coupon_ref.add(key)
        out.setdefault("coupon_uses", []).append(dict(coupon_code=code, user_id=cu["user_id"], ref_type=ref_type,
            ref_id=cu["ref_id"], created_at=parse_ts(cu.get("created_at")) or datetime.now(timezone.utc)))

    for a in data["assistant_actions"]:
        if (a.get("status") or "pending") == "pending":
            report["skipped"]["pending_assistant_actions"] += 1
            continue
        try:
            args = json.loads(a.get("args") or "{}")
            if not isinstance(args, dict):
                args = {"legacy": args}
        except (TypeError, ValueError):
            args = {"legacy": a.get("args")}
        out.setdefault("assistant_actions", []).append(dict(id=a["id"], user_id=a["user_id"], tool=(a.get("action") or "")[:40],
            args=args, summary=(a.get("summary") or "")[:500], status=a.get("status") or "expired",
            result=a.get("result") or "", expires_at=parse_ts(a.get("expires_at")) or datetime.now(timezone.utc),
            created_at=parse_ts(a.get("created_at")) or datetime.now(timezone.utc)))

    report["skipped"]["legacy_otp_codes"] = len(data.get("otp_codes", [])) if "otp_codes" in data else 0
    report["counts"] = {k: len(v) for k, v in out.items()}
    return out


TABLES = {"users": User, "addresses": Address, "products": Product, "coupons": Coupon, "vehicles": Vehicle,
          "drivers": Driver, "routes": Route, "orders": Order, "order_items": OrderItem, "route_stops": RouteStop,
          "trips": Trip, "payments": Payment, "refunds": Refund, "wallet_transactions": WalletTransaction,
          "alerts": Alert, "notifications": Notification, "audit_logs": AuditLog,
          "maintenance_records": Maintenance, "coupon_uses": CouponUse, "assistant_actions": AssistantAction}
INSERT_ORDER = list(TABLES)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, type=Path, help="Legacy SQLite database file (opened read-only)")
    ap.add_argument("--database-url", default=None, help="Target PostgreSQL URL (default: DATABASE_URL from .env)")
    ap.add_argument("--apply", action="store_true", help="Write to PostgreSQL (default is dry-run)")
    ap.add_argument("--report", type=Path, default=None, help="Write a JSON migration report here")
    args = ap.parse_args()

    url = args.database_url or get_settings().database_url
    if not url.startswith("postgresql"):
        raise SystemExit("Target must be PostgreSQL; SQLite is not a v3 runtime database")
    engine = create_engine(url, connect_args={"connect_timeout": 10, "application_name": "routenex-migration"})
    report = {"source": str(args.source), "target": url.split("@")[-1], "applied": False,
              "counts": {}, "errors": [], "skipped": {"zero_amount_payments": 0, "orphan_coupon_uses": 0,
              "duplicate_coupon_uses": 0, "pending_assistant_actions": 0, "legacy_otp_codes": 0},
              "assumptions": {"delivery_windows_defaulted": 0, "address_coordinates_defaulted": 0,
                              "order_route_links_dropped": 0, "handover_otps_rotated": 0}}
    try:
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            if version != HEAD:
                raise MigrationError(f"Target schema is {version!r}; run 'alembic upgrade head' first (expected {HEAD})")
            for model in EMPTY_CHECK:
                n = conn.execute(select(func.count()).select_from(model)).scalar()
                if n:
                    raise MigrationError(f"Target table {model.__tablename__} is not empty ({n} rows). Migrate into a fresh database before bootstrap.")
        data = read_source(args.source)
        rows = build(data, report)
        if report["errors"]:
            raise MigrationError("Source data failed validation:\n  - " + "\n  - ".join(report["errors"][:40]))
        if args.apply:
            with engine.begin() as conn:
                for name in INSERT_ORDER:
                    batch = rows.get(name, [])
                    if batch:
                        conn.execute(TABLES[name].__table__.insert(), batch)
                for model in SERIAL_MODELS:
                    table = model.__tablename__
                    seq = conn.execute(text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": table}).scalar()
                    max_id = conn.execute(select(func.max(model.id))).scalar()
                    if seq and max_id:
                        conn.execute(text("SELECT setval(CAST(:seq AS regclass), :v, true)"), {"seq": seq, "v": max_id})
            report["applied"] = True
        print(json.dumps(report, indent=2, default=str))
        if args.report:
            args.report.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        if not args.apply:
            print("\nDry-run only. Re-run with --apply to import.", file=sys.stderr)
    except MigrationError as exc:
        print(json.dumps(report, indent=2, default=str), file=sys.stderr)
        raise SystemExit(str(exc))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
