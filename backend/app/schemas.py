"""Strict API inputs: prices, roles, stock and payment success are never client-controlled."""
from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Input):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    @field_validator("email")
    @classmethod
    def lower_email(cls, value): return value.lower()


class Register(Login):
    name: str = Field(min_length=2, max_length=120)


class PhoneInput(Input):
    phone: str = Field(pattern=r"^\+[1-9]\d{7,14}$")


class OtpVerify(PhoneInput):
    code: str = Field(pattern=r"^\d{6}$")


class GoogleInput(Input):
    credential: str = Field(min_length=20, max_length=8000)


class ProfileInput(Input):
    name: str = Field(min_length=2, max_length=120)


class PasswordInput(Input):
    current_password: str = Field(max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class Coordinates(Input):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class AddressInput(Coordinates):
    label: str = Field(min_length=1, max_length=40)
    line1: str = Field(min_length=5, max_length=240)
    city: str = Field(default="Jaipur", min_length=2, max_length=80)
    state: str = Field(default="Rajasthan", min_length=2, max_length=80)
    pincode: str = Field(pattern=r"^\d{6}$")


class CartInput(Input):
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=0, le=50)


class CheckoutInput(Input):
    address_id: int = Field(gt=0)
    payment_method: Literal["cod", "wallet", "razorpay"] = "cod"
    coupon: str | None = Field(default=None, max_length=30)
    priority: int = Field(default=1, ge=1, le=5)
    delivery_window_start: datetime
    delivery_window_end: datetime
    idempotency_key: str = Field(min_length=8, max_length=80)
    @model_validator(mode="after")
    def dates(self):
        if self.delivery_window_start.tzinfo is None or self.delivery_window_end.tzinfo is None:
            raise ValueError("Delivery windows must include a timezone")
        if self.delivery_window_end <= self.delivery_window_start:
            raise ValueError("Delivery window end must be after its start")
        return self


class PlaceInput(Coordinates):
    name: str = Field(min_length=2, max_length=240)


class TripQuoteInput(Input):
    kind: Literal["ride", "parcel"] = "ride"
    pickup: PlaceInput
    drop: PlaceInput
    weight_kg: float = Field(default=1, gt=0, le=900)
    parcel_size: Literal["small", "medium", "large"] = "small"
    fragile: bool = False


class BookTripInput(Input):
    quote_token: str = Field(min_length=20, max_length=6000)
    vehicle_class: str = Field(pattern=r"^(bike|auto|cab|pbike|pmini|pvan)$")
    payment_method: Literal["cash", "wallet", "razorpay"] = "cash"
    coupon: str | None = Field(default=None, max_length=30)
    recipient_name: str | None = Field(default=None, max_length=120)
    recipient_phone: str | None = Field(default=None, pattern=r"^\+[1-9]\d{7,14}$")
    description: str | None = Field(default=None, max_length=240)
    idempotency_key: str = Field(min_length=8, max_length=80)


class ProofInput(Input):
    code: str = Field(pattern=r"^\d{6}$")


class CancelInput(Input):
    reason: str = Field(default="Changed my plans", min_length=3, max_length=240)


class RatingInput(Input):
    rating: int = Field(ge=1, le=5)
    review: str = Field(default="", max_length=500)


class PaymentCreate(Input):
    purpose: Literal["order", "trip", "wallet_topup"]
    reference_id: int | None = None
    amount: Decimal | None = Field(default=None, gt=0, le=100000)
    idempotency_key: str = Field(min_length=8, max_length=80)
    @model_validator(mode="after")
    def reference(self):
        if self.purpose != "wallet_topup" and not self.reference_id:
            raise ValueError("reference_id is required")
        if self.purpose == "wallet_topup" and self.amount is None:
            raise ValueError("amount is required for wallet top-ups")
        return self


class PaymentVerify(Input):
    razorpay_order_id: str = Field(max_length=80)
    razorpay_payment_id: str = Field(max_length=80)
    razorpay_signature: str = Field(pattern=r"^[a-fA-F0-9]{64}$")


class DemoPaymentInput(Input):
    outcome: Literal["success", "failure"] = "success"


class RefundInput(Input):
    reason: str = Field(min_length=5, max_length=240)
    amount: Decimal | None = Field(default=None, gt=0)
    cash_returned: bool = False


class OptimizerInput(Input):
    traffic_factor: float = Field(default=1.0, ge=0.8, le=2.0)
    time_limit_seconds: float = Field(default=1.5, ge=0.2, le=5.0)


class ApplyPlan(Input):
    plan_id: str = Field(pattern=r"^[a-f0-9-]{36}$")


class VehicleInput(Input):
    plate: str = Field(min_length=6, max_length=20)
    type: Literal["Bike", "Electric Cargo", "Mini Van", "Van", "Pickup", "Reefer Van", "Truck", "EV Van", "Auto", "Cab"]
    capacity_kg: float = Field(gt=0, le=30000)
    cost_per_km: Decimal = Field(default=Decimal("10"), gt=0, le=1000)
    lat: float = Field(default=26.9124, ge=-90, le=90)
    lng: float = Field(default=75.7873, ge=-180, le=180)
    documents: str = Field(default="Verified", max_length=240)


class VehicleUpdate(Input):
    status: Literal["available", "maintenance", "breakdown", "retired"]
    reason: str = Field(default="Fleet status update", min_length=3, max_length=240)


class DriverInput(Input):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    license_number: str = Field(min_length=5, max_length=40)
    vehicle_id: int | None = None
    service: Literal["ride", "delivery", "both"] = "both"


class DriverUpdate(Input):
    online: bool | None = None
    vehicle_id: int | None = None
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class EventInput(Input):
    event: Literal["traffic", "delay", "breakdown", "maintenance", "document", "capacity", "other"]
    message: str = Field(min_length=5, max_length=500)
    entity_type: Literal["vehicle", "driver", "order", "route", "network"] = "network"
    entity_id: int | None = None


class ActiveInput(Input):
    active: bool


class UserRoleInput(Input):
    role: Literal["customer", "driver", "dispatcher", "fleet_manager", "admin"]


class ProductInput(Input):
    name: str = Field(min_length=3, max_length=180)
    description: str = Field(min_length=10, max_length=2000)
    category: str = Field(min_length=2, max_length=80)
    brand: str = Field(default="RouteNex Essentials", max_length=80)
    unit: str = Field(default="1 piece", max_length=40)
    price: Decimal = Field(gt=0, le=1000000)
    stock: int = Field(ge=0, le=100000)
    weight_grams: int = Field(gt=0, le=100000)
    image_path: str = Field(default="", max_length=240)


class ProductUpdate(Input):
    price: Decimal | None = Field(default=None, gt=0, le=1000000)
    stock: int | None = Field(ge=0, le=100000)
    active: bool | None = None


class MaintenanceInput(Input):
    vehicle_id: int
    description: str = Field(min_length=5, max_length=500)
    scheduled_for: datetime


class AssistantInput(Input):
    message: str = Field(min_length=1, max_length=1000)


class AssistantConfirm(Input):
    action_id: int


class TrainingInput(Input):
    source: Literal["synthetic"] = "synthetic"
    eta_rows: int = Field(default=6000, ge=1000, le=40000)
    delay_rows: int = Field(default=5000, ge=1000, le=30000)
    days: int = Field(default=40, ge=30, le=70)
