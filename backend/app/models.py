"""Relational domain model for PostgreSQL.

Money is stored as integer paise, timestamps are timezone-aware, and state
changes are protected by checks, foreign keys and partial unique indexes.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def public_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=utcnow, nullable=False)


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default="customer")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    wallet_balance_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    addresses: Mapped[list["Address"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    __table_args__ = (
        CheckConstraint("role IN ('customer','driver','dispatcher','fleet_manager','admin')", name="ck_users_role"),
        CheckConstraint("wallet_balance_paise >= 0", name="ck_users_wallet_nonnegative"),
        CheckConstraint("email IS NOT NULL OR phone IS NOT NULL", name="ck_users_contact"),
    )


class UserSession(Base):
    __tablename__ = "user_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=public_id)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    ip_address: Mapped[str] = mapped_column(String(45), default="")
    user_agent: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped[User] = relationship()


class LoginEvent(Base):
    __tablename__ = "login_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(254), default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    success: Mapped[bool] = mapped_column(Boolean)
    method: Mapped[str] = mapped_column(String(20), default="password")
    reason: Mapped[str] = mapped_column(String(120), default="")
    ip_address: Mapped[str] = mapped_column(String(45), default="")
    user_agent: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class RateLimit(Base):
    __tablename__ = "rate_limits"
    key: Mapped[str] = mapped_column(String(250), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    count: Mapped[int] = mapped_column(Integer, default=0)


class OtpCode(Base):
    __tablename__ = "otp_codes"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    purpose: Mapped[str] = mapped_column(String(20), default="login")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    consumed: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Address(Base):
    __tablename__ = "addresses"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(40))
    line1: Mapped[str] = mapped_column(String(240))
    city: Mapped[str] = mapped_column(String(80), default="Jaipur")
    state: Mapped[str] = mapped_column(String(80), default="Rajasthan")
    pincode: Mapped[str] = mapped_column(String(6))
    lat: Mapped[float] = mapped_column(Numeric(9, 6))
    lng: Mapped[float] = mapped_column(Numeric(9, 6))
    user: Mapped[User] = relationship(back_populates="addresses")
    __table_args__ = (CheckConstraint("lat BETWEEN -90 AND 90 AND lng BETWEEN -180 AND 180"),)


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True)
    slug: Mapped[str] = mapped_column(String(180), unique=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(80), index=True)
    brand: Mapped[str] = mapped_column(String(80), default="RouteNex Essentials")
    unit: Mapped[str] = mapped_column(String(40), default="1 piece")
    price_paise: Mapped[int] = mapped_column(BigInteger)
    compare_at_paise: Mapped[int | None] = mapped_column(BigInteger)
    stock: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    weight_grams: Mapped[int] = mapped_column(Integer, default=100)
    image_path: Mapped[str] = mapped_column(String(240), default="")
    image_credit: Mapped[str] = mapped_column(String(240), default="")
    rating: Mapped[float] = mapped_column(Numeric(2, 1), default=4.5)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        CheckConstraint("price_paise > 0 AND stock >= 0 AND reserved >= 0 AND reserved <= stock AND weight_grams > 0"),
        CheckConstraint("rating BETWEEN 0 AND 5"),
    )


class CartItem(Base):
    __tablename__ = "cart_items"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    quantity: Mapped[int] = mapped_column(Integer)
    product: Mapped[Product] = relationship()
    __table_args__ = (CheckConstraint("quantity BETWEEN 1 AND 50"),)


class Coupon(Base):
    __tablename__ = "coupons"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    title: Mapped[str] = mapped_column(String(180))
    scope: Mapped[str] = mapped_column(String(20), default="all")
    kind: Mapped[str] = mapped_column(String(10), default="percent")
    value: Mapped[int] = mapped_column(Integer)
    max_discount_paise: Mapped[int | None] = mapped_column(BigInteger)
    min_amount_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    one_time: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("scope IN ('all','shop','ride','parcel')"), CheckConstraint("kind IN ('percent','flat') AND value > 0"))


class CouponUse(Base):
    __tablename__ = "coupon_uses"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    coupon_code: Mapped[str] = mapped_column(ForeignKey("coupons.code"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ref_type: Mapped[str] = mapped_column(String(10))
    ref_id: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("ref_type", "ref_id", name="uq_coupon_reference"),)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    address_id: Mapped[int] = mapped_column(ForeignKey("addresses.id"))
    status: Mapped[str] = mapped_column(String(24), default="awaiting_payment", index=True)
    subtotal_paise: Mapped[int] = mapped_column(BigInteger)
    discount_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    delivery_fee_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    coupon_code: Mapped[str | None] = mapped_column(String(30))
    payment_method: Mapped[str] = mapped_column(String(16), default="cod")
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")
    priority: Mapped[int] = mapped_column(Integer, default=1)
    delivery_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivery_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    delivery_otp_hash: Mapped[str | None] = mapped_column(String(64))
    delivery_otp_encrypted: Mapped[str | None] = mapped_column(Text)
    weight_grams: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    reservation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    route_id: Mapped[int | None] = mapped_column(ForeignKey("routes.id", ondelete="SET NULL"), index=True)
    address: Mapped[Address] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_order_idempotency"),
        CheckConstraint("status IN ('awaiting_payment','placed','assigned','picked_up','out_for_delivery','delivered','cancelled','failed')"),
        CheckConstraint("payment_method IN ('cod','wallet','razorpay')"),
        CheckConstraint("priority BETWEEN 1 AND 5 AND total_paise >= 0 AND discount_paise >= 0"),
        CheckConstraint("delivery_window_end > delivery_window_start"),
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(180))
    sku: Mapped[str] = mapped_column(String(40))
    unit_price_paise: Mapped[int] = mapped_column(BigInteger)
    quantity: Mapped[int] = mapped_column(Integer)
    weight_grams: Mapped[int] = mapped_column(Integer)
    order: Mapped[Order] = relationship(back_populates="items")
    __table_args__ = (CheckConstraint("quantity > 0 AND unit_price_paise >= 0"),)


class Vehicle(TimestampMixin, Base):
    __tablename__ = "vehicles"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    plate: Mapped[str] = mapped_column(String(20), unique=True)
    type: Mapped[str] = mapped_column(String(40))
    capacity_kg: Mapped[float] = mapped_column(Numeric(8, 2))
    cost_per_km_paise: Mapped[int] = mapped_column(Integer, default=1000)
    status: Mapped[str] = mapped_column(String(20), default="available", index=True)
    lat: Mapped[float | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[float | None] = mapped_column(Numeric(9, 6))
    documents: Mapped[str] = mapped_column(String(240), default="Pending verification")
    next_maintenance: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("status IN ('available','assigned','maintenance','breakdown','retired')"), CheckConstraint("capacity_kg > 0"))


class Driver(TimestampMixin, Base):
    __tablename__ = "drivers"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"))
    license_number: Mapped[str] = mapped_column(String(40))
    documents: Mapped[str] = mapped_column(String(240), default="Pending verification")
    service: Mapped[str] = mapped_column(String(12), default="both")
    online: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="available")
    lat: Mapped[float | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[float | None] = mapped_column(Numeric(9, 6))
    rating: Mapped[float] = mapped_column(Numeric(2, 1), default=5.0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    user: Mapped[User] = relationship()
    vehicle: Mapped[Vehicle | None] = relationship()
    __table_args__ = (CheckConstraint("service IN ('ride','delivery','both')"), CheckConstraint("status IN ('available','assigned','on_trip','offline')"))


class Trip(TimestampMixin, Base):
    __tablename__ = "trips"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    driver_id: Mapped[int | None] = mapped_column(ForeignKey("drivers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(10), default="ride")
    vehicle_class: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(16), default="searching", index=True)
    pickup_name: Mapped[str] = mapped_column(String(240))
    pickup_lat: Mapped[float] = mapped_column(Numeric(9, 6))
    pickup_lng: Mapped[float] = mapped_column(Numeric(9, 6))
    drop_name: Mapped[str] = mapped_column(String(240))
    drop_lat: Mapped[float] = mapped_column(Numeric(9, 6))
    drop_lng: Mapped[float] = mapped_column(Numeric(9, 6))
    distance_km: Mapped[float] = mapped_column(Numeric(8, 2))
    fare_paise: Mapped[int] = mapped_column(BigInteger)
    discount_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    total_paise: Mapped[int] = mapped_column(BigInteger)
    eta_min: Mapped[int] = mapped_column(Integer)
    eta_source: Mapped[str] = mapped_column(String(16), default="formula")
    payment_method: Mapped[str] = mapped_column(String(16), default="cash")
    payment_status: Mapped[str] = mapped_column(String(20), default="pending")
    coupon_code: Mapped[str | None] = mapped_column(String(30))
    pickup_otp_hash: Mapped[str] = mapped_column(String(64))
    delivery_otp_hash: Mapped[str | None] = mapped_column(String(64))
    pickup_otp_encrypted: Mapped[str | None] = mapped_column(Text)
    delivery_otp_encrypted: Mapped[str | None] = mapped_column(Text)
    recipient_name: Mapped[str | None] = mapped_column(String(120))
    recipient_phone: Mapped[str | None] = mapped_column(String(20))
    weight_kg: Mapped[float | None] = mapped_column(Numeric(8, 2))
    parcel_size: Mapped[str | None] = mapped_column(String(10))
    fragile: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(String(240))
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(80))
    search_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str | None] = mapped_column(String(240))
    rating: Mapped[int | None] = mapped_column(Integer)
    review: Mapped[str | None] = mapped_column(String(500))
    driver: Mapped[Driver | None] = relationship()
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_trip_idempotency"),
        Index("uq_active_trip_driver", "driver_id", unique=True, postgresql_where=text("status IN ('matched','arrived','started')")),
        CheckConstraint("kind IN ('ride','parcel')"),
        CheckConstraint("status IN ('awaiting_payment','searching','matched','arrived','started','completed','cancelled','expired')", name="ck_trips_status"),
        CheckConstraint("payment_method IN ('cash','wallet','razorpay')"),
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5"),
    )


class RoutePlan(Base):
    __tablename__ = "route_plans"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=public_id)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), default="preview")
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    state_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (CheckConstraint("status IN ('preview','applied','expired','rejected')"),)


class Route(TimestampMixin, Base):
    __tablename__ = "routes"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    plan_id: Mapped[str | None] = mapped_column(ForeignKey("route_plans.id", ondelete="SET NULL"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"))
    status: Mapped[str] = mapped_column(String(20), default="planned")
    distance_km: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    duration_min: Mapped[int] = mapped_column(Integer, default=0)
    cost_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    load_kg: Mapped[float] = mapped_column(Numeric(8, 2), default=0)
    geometry: Mapped[list] = mapped_column(JSONB, default=list)
    reason: Mapped[str] = mapped_column(String(240), default="")
    vehicle: Mapped[Vehicle] = relationship()
    driver: Mapped[Driver] = relationship()
    stops: Mapped[list["RouteStop"]] = relationship(back_populates="route", cascade="all, delete-orphan", order_by="RouteStop.sequence")
    __table_args__ = (
        CheckConstraint("status IN ('planned','active','completed','reroute_required','cancelled')"),
        Index("uq_active_route_vehicle", "vehicle_id", unique=True, postgresql_where=text("status IN ('planned','active')")),
        Index("uq_active_route_driver", "driver_id", unique=True, postgresql_where=text("status IN ('planned','active')")),
    )


class RouteStop(Base):
    __tablename__ = "route_stops"
    route_id: Mapped[int] = mapped_column(ForeignKey("routes.id", ondelete="CASCADE"), primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), primary_key=True, unique=True)
    sequence: Mapped[int] = mapped_column(Integer)
    eta: Mapped[str] = mapped_column(String(12))
    arrival_min: Mapped[int] = mapped_column(Integer)
    delay_risk: Mapped[float | None] = mapped_column(Numeric(4, 3))
    route: Mapped[Route] = relationship(back_populates="stops")
    __table_args__ = (UniqueConstraint("route_id", "sequence"), CheckConstraint("sequence > 0"))


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    public_id: Mapped[str] = mapped_column(String(36), unique=True, default=public_id)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    reference_id: Mapped[int | None] = mapped_column(BigInteger)
    provider: Mapped[str] = mapped_column(String(16))
    provider_order_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    provider_payment_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="created", index=True)
    method: Mapped[str] = mapped_column(String(20), default="")
    idempotency_key: Mapped[str] = mapped_column(String(80))
    receipt: Mapped[str] = mapped_column(String(80), unique=True)
    failure_reason: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_payment_idempotency"),
        CheckConstraint("purpose IN ('order','trip','wallet_topup')"),
        CheckConstraint("provider IN ('demo','razorpay','wallet','cash')"),
        CheckConstraint("status IN ('created','authorized','captured','failed','refund_pending','refunded')"),
        CheckConstraint("amount_paise > 0 AND currency = 'INR'"),
    )


class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True)
    provider_refund_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="initiated")
    reason: Mapped[str] = mapped_column(String(240), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("amount_paise > 0"), CheckConstraint("status IN ('initiated','processed','failed')"))


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    provider: Mapped[str] = mapped_column(String(16))
    event_id: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict] = mapped_column(JSONB)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="received")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_event"),)


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    payment_id: Mapped[int | None] = mapped_column(ForeignKey("payments.id"))
    amount_paise: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(20))
    balance_after_paise: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    message: Mapped[str] = mapped_column(String(500))
    entity_type: Mapped[str] = mapped_column(String(30), default="")
    entity_id: Mapped[int | None] = mapped_column(BigInteger)
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(String(1000))
    read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(60), default="")
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    ip_address: Mapped[str] = mapped_column(String(45), default="")
    request_id: Mapped[str] = mapped_column(String(36), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class LocationCache(Base):
    __tablename__ = "location_cache"
    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20))
    results: Mapped[list] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AssistantAction(Base):
    __tablename__ = "assistant_actions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    tool: Mapped[str] = mapped_column(String(40))
    args: Mapped[dict] = mapped_column(JSONB, default=dict)
    summary: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    result: Mapped[str] = mapped_column(Text, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TrainingJob(Base):
    __tablename__ = "training_jobs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    requested_by: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    report: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DriverEarning(Base):
    __tablename__ = "driver_earnings"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    driver_id: Mapped[int] = mapped_column(ForeignKey("drivers.id"), index=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), unique=True)
    gross_paise: Mapped[int] = mapped_column(BigInteger)
    platform_fee_paise: Mapped[int] = mapped_column(BigInteger)
    net_paise: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default="payable")
    settlement_reference: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("status IN ('payable','paid')"), CheckConstraint("gross_paise >= 0 AND net_paise >= 0 AND gross_paise = platform_fee_paise + net_paise"))


class Maintenance(Base):
    __tablename__ = "maintenance_records"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"), index=True)
    description: Mapped[str] = mapped_column(String(500))
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="scheduled")
    cost_paise: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
