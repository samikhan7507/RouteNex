"""Ride/parcel lifecycle with atomic driver claims and proof-of-handover codes."""
from __future__ import annotations
import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import protect_code
from app.models import Alert, Driver, DriverEarning, Trip, User, Vehicle, utcnow
from app.services import payments
from app.services.common import audit, notify
from app.services.geo import haversine_km

MATCH_LOCK = 742002
CLASS_VEHICLES = {"bike": ("Bike",), "auto": ("Auto",), "cab": ("Cab",), "pbike": ("Bike",),
                  "pmini": ("Electric Cargo", "Mini Van", "EV Van"), "pvan": ("Van", "Pickup", "Mini Van")}
ACTIVE = ("awaiting_payment", "searching", "matched", "arrived", "started")


def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def code_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()


def check_code(db: Session, trip: Trip, code: str, purpose: str):
    from app.core.ratelimit import consume
    consume(db, f"trip-proof:{trip.id}:{purpose}", 5, 300, commit=True)
    expected = trip.pickup_otp_hash if purpose == "pickup" else trip.delivery_otp_hash
    if not expected or not hmac.compare_digest(expected, code_hash(code)):
        raise HTTPException(400, "Incorrect handover code. Ask the customer/recipient to check it")


def create(db: Session, user: User, payload, quote: dict) -> Trip:
    db.scalar(select(User).where(User.id == user.id).with_for_update())
    existing = db.scalar(select(Trip).where(Trip.user_id == user.id, Trip.idempotency_key == payload.idempotency_key))
    if existing:
        return existing
    selected = next((q for q in quote["quotes"] if q["vehicle_class"] == payload.vehicle_class), None)
    if not selected or quote["kind"] != quote["kind"]:
        raise HTTPException(422, "Selected vehicle is not available for this quote")
    limit = 1 if quote["kind"] == "ride" else 5
    active = db.scalar(select(func.count(Trip.id)).where(Trip.user_id == user.id, Trip.kind == quote["kind"], Trip.status.in_(ACTIVE)))
    if active >= limit:
        raise HTTPException(409, f"You already have the maximum active {'ride' if limit == 1 else 'parcels'} for this service")
    from app.services.coupons import evaluate, record
    discount, code = evaluate(db, user.id, payload.coupon, selected["fare_paise"], quote["kind"])
    if quote["kind"] == "parcel" and (not payload.recipient_name or not payload.recipient_phone):
        raise HTTPException(422, "Recipient name and phone are required for a parcel")
    pickup, drop = quote["pickup"], quote["drop"]
    pickup_code, delivery_code = new_code(), new_code()
    razorpay = payload.payment_method == "razorpay" and selected["fare_paise"] - discount > 0
    trip = Trip(user_id=user.id, kind=quote["kind"], vehicle_class=payload.vehicle_class,
                status="awaiting_payment" if razorpay else "searching",
                pickup_name=pickup["name"], pickup_lat=pickup["lat"], pickup_lng=pickup["lng"],
                drop_name=drop["name"], drop_lat=drop["lat"], drop_lng=drop["lng"],
                distance_km=quote["distance_km"], fare_paise=selected["fare_paise"], discount_paise=discount,
                total_paise=selected["fare_paise"] - discount, eta_min=selected["eta_min"], eta_source=quote["distance_source"],
                payment_method=payload.payment_method, payment_status="pending", coupon_code=code,
                pickup_otp_hash=code_hash(pickup_code), pickup_otp_encrypted=protect_code(pickup_code),
                delivery_otp_hash=code_hash(delivery_code) if quote["kind"] == "parcel" else None,
                delivery_otp_encrypted=protect_code(delivery_code) if quote["kind"] == "parcel" else None,
                recipient_name=payload.recipient_name, recipient_phone=payload.recipient_phone,
                description=payload.description, weight_kg=quote.get("weight_kg"), parcel_size=quote.get("parcel_size"),
                fragile=quote.get("fragile", False), simulated=get_settings().demo_mode and get_settings().demo_autopilot,
                idempotency_key=payload.idempotency_key)
    db.add(trip)
    db.flush()
    if not razorpay:
        payments.instant_payment(db, user, "trip", trip, payload.payment_method)
    record(db, user.id, code, "trip", trip.id)
    notify(db, user.id, "Parcel booked" if trip.kind == "parcel" else "Ride requested",
           "Share the delivery code with your recipient; the driver must enter it to complete the parcel." if trip.kind == "parcel" else "Your pickup code is available in trip details. Share it only with your assigned driver.")
    audit(db, user, "CREATE", "trip", trip.id, {"kind": trip.kind, "total_paise": trip.total_paise, "simulated": trip.simulated})
    return trip


def eligible_drivers(db: Session, trip: Trip):
    service = "delivery" if trip.kind == "parcel" else "ride"
    query = select(Driver).join(User).join(Vehicle).where(Driver.status == "available", Driver.online.is_(True),
                    Driver.service.in_([service, "both"]), Driver.documents == "Verified", User.active.is_(True),
                    Vehicle.status == "available", Vehicle.type.in_(CLASS_VEHICLES[trip.vehicle_class]),
                    Vehicle.capacity_kg >= (trip.weight_kg or 0)).with_for_update()
    drivers = list(db.scalars(query))
    return sorted(drivers, key=lambda d: haversine_km(float(trip.pickup_lat), float(trip.pickup_lng), float(d.lat or 0), float(d.lng or 0)))


def match(db: Session, trip: Trip, chosen: Driver | None = None) -> bool:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": MATCH_LOCK})
    trip = db.scalar(select(Trip).where(Trip.id == trip.id).with_for_update())
    if trip.status != "searching":
        return False
    drivers = eligible_drivers(db, trip)
    driver = chosen or next((d for d in drivers if haversine_km(float(trip.pickup_lat), float(trip.pickup_lng), float(d.lat or 0), float(d.lng or 0)) <= 25), None)
    if not driver or (chosen and chosen.id not in {d.id for d in drivers}):
        return False
    trip.driver_id, trip.status, trip.matched_at = driver.id, "matched", utcnow()
    driver.status, driver.vehicle.status = "assigned", "assigned"
    notify(db, trip.user_id, "Driver assigned", f"{driver.user.name} will arrive in {driver.vehicle.plate}. Your pickup code is in trip details.")
    audit(db, None, "TRIP_MATCH", "trip", trip.id, {"driver_id": driver.id, "simulated": trip.simulated})
    return True


def release_driver(db: Session, trip: Trip):
    if trip.driver:
        trip.driver.status = "available" if trip.driver.online else "offline"
        trip.driver.vehicle.status = "available"
        trip.driver.lat, trip.driver.lng = trip.drop_lat, trip.drop_lng


def cancel(db: Session, user: User, trip: Trip, reason: str):
    db.scalar(select(User).where(User.id == trip.user_id).with_for_update())
    trip = db.scalar(select(Trip).where(Trip.id == trip.id).with_for_update())
    if trip.status in ("completed", "cancelled", "expired"):
        raise HTTPException(409, "This trip is already closed")
    if user.role == "customer" and trip.status == "started":
        raise HTTPException(409, "A trip in progress cannot be cancelled here. Contact support")
    trip.status, trip.cancelled_at, trip.cancel_reason = "cancelled", utcnow(), reason
    release_driver(db, trip)
    from app.models import Payment
    payment = db.scalar(select(Payment).where(Payment.purpose == "trip", Payment.reference_id == trip.id).with_for_update())
    if payment and payment.status == "captured":
        payments.refund(db, user, payment, payment.amount_paise, f"Trip cancelled: {reason}")
    elif payment and payment.status == "created":
        payment.status, payment.failure_reason = "failed", "Trip cancelled before collection"
        trip.payment_status = "cancelled"
    notify(db, trip.user_id, "Trip cancelled", reason)
    audit(db, user, "CANCEL", "trip", trip.id, {"reason": reason})


def advance(db: Session, user: User, trip: Trip, action: str, code: str | None = None):
    trip = db.scalar(select(Trip).where(Trip.id == trip.id).with_for_update())
    if not trip.driver or trip.driver.user_id != user.id:
        raise HTTPException(403, "This trip is not assigned to you")
    if action == "arrive" and trip.status == "matched":
        trip.status, trip.arrived_at = "arrived", utcnow()
        notify(db, trip.user_id, "Driver has arrived", "Meet your driver at the pickup point and share your pickup code.")
    elif action == "start" and trip.status == "arrived":
        check_code(db, trip, code or "", "pickup")
        trip.status, trip.started_at, trip.driver.status = "started", utcnow(), "on_trip"
    elif action == "complete" and trip.status == "started":
        if trip.kind == "parcel":
            check_code(db, trip, code or "", "delivery")
        if trip.payment_method == "cash":
            payments.settle_cash(db, "trip", trip)
        trip.status, trip.completed_at = "completed", utcnow()
        release_driver(db, trip)
        # Truncate fractional paise from driver net; the fee retains the remainder so gross = net + fee.
        net = trip.total_paise * 80 // 100
        db.add(DriverEarning(driver_id=trip.driver_id, trip_id=trip.id, gross_paise=trip.total_paise,
                             platform_fee_paise=trip.total_paise - net, net_paise=net))
        notify(db, trip.user_id, "Trip completed", "Thank you for travelling with RouteNex. You can now rate your driver.")
    else:
        raise HTTPException(409, f"Cannot {action} a trip that is {trip.status}")
    audit(db, user, f"TRIP_{action.upper()}", "trip", trip.id)


def tick(db: Session):
    """Demo-only automatic matching; real drivers must explicitly accept requests."""
    settings = get_settings()
    now = utcnow()
    # Expire abandoned checkout/search reservations.
    from app.models import Payment
    for trip in db.scalars(select(Trip).where(Trip.status == "awaiting_payment", Trip.search_started_at < now - timedelta(minutes=settings.reservation_minutes)).with_for_update()):
        payment = db.scalar(select(Payment).where(Payment.purpose == "trip", Payment.reference_id == trip.id).with_for_update())
        if payment and payment.status == "created":
            payments.fail(db, payment, "Checkout reservation expired")
        else:
            trip.status, trip.payment_status = "expired", "failed"
    for trip in db.scalars(select(Trip).where(Trip.status == "searching", Trip.search_started_at < now - timedelta(minutes=10)).with_for_update()):
        trip.status = "expired"
        payment = db.scalar(select(Payment).where(Payment.purpose == "trip", Payment.reference_id == trip.id).with_for_update())
        if payment and payment.status == "captured":
            payments.refund(db, db.get(User, trip.user_id), payment, payment.amount_paise, "No driver was available; automatic refund")
        else:
            trip.payment_status = "cancelled"
            if payment:
                payment.status = "failed"
        db.add(Alert(type="no_driver", severity="medium", message=f"No driver accepted trip #{trip.id}", entity_type="trip", entity_id=trip.id))
    if settings.demo_mode and settings.demo_autopilot:
        for trip in db.scalars(select(Trip).where(Trip.status == "searching", Trip.simulated.is_(True), Trip.search_started_at < now - timedelta(seconds=4)).limit(20)):
            match(db, trip)
