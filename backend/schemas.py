from typing import Optional, Literal
from pydantic import BaseModel, Field

PayMethod = Literal["cash", "wallet", "upi", "card"]


class Login(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=128)

class PhoneIn(BaseModel):
    phone: str = Field(pattern=r"^\d{10}$")

class OtpVerify(PhoneIn):
    code: str = Field(pattern=r"^\d{6}$")

class GoogleIn(BaseModel):
    demo: bool = False

class Address(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    line1: str = Field(min_length=3, max_length=200)
    city: str = Field("Jaipur", max_length=60)
    state: str = Field("Rajasthan", max_length=60)
    pincode: str = Field(pattern=r"^\d{6}$")
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)

class CartItem(BaseModel):
    item_id: int
    quantity: int = Field(ge=1, le=50)

class OrderIn(BaseModel):
    address_id: int
    priority: int = Field(1, ge=1, le=5)
    delivery_window: str = Field("Today 18:00", max_length=40)
    items: list[CartItem] = Field(min_length=1, max_length=30)
    payment_method: Literal["cod", "wallet", "upi", "card"] = "cod"
    coupon: Optional[str] = Field(None, max_length=20)

class TripBase(BaseModel):
    pickup: str = Field(min_length=1, max_length=200)
    pickup_lat: float = Field(ge=-90, le=90)
    pickup_lng: float = Field(ge=-180, le=180)
    dropoff: str = Field(min_length=1, max_length=200)
    drop_lat: float = Field(ge=-90, le=90)
    drop_lng: float = Field(ge=-180, le=180)
    route_distance_km: Optional[float] = Field(None, gt=0, le=500)
    route_duration_min: Optional[float] = Field(None, gt=0, le=1440)
    payment_method: PayMethod = "cash"
    coupon: Optional[str] = Field(None, max_length=20)

class RideIn(TripBase):
    vehicle_class: Literal["bike", "auto", "cab"] = "cab"

class ParcelIn(TripBase):
    weight_kg: float = Field(gt=0, le=900)
    size: Literal["small", "medium", "large"] = "small"
    fragile: bool = False
    description: str = Field("", max_length=120)
    recipient_name: str = Field("", max_length=60)
    recipient_phone: str = Field("", max_length=15)
    vehicle_class: Optional[Literal["pbike", "pmini", "pvan"]] = None

class OtpIn(BaseModel):
    otp: str = Field(pattern=r"^\d{4}$")

class CompleteIn(BaseModel):
    otp: Optional[str] = Field(None, pattern=r"^\d{4}$")

class CancelIn(BaseModel):
    reason: str = Field("Changed my mind", max_length=120)

class RateIn(BaseModel):
    rating: int = Field(ge=1, le=5)
    review: str = Field("", max_length=300)

class OnlineIn(BaseModel):
    online: bool

class TopupIn(BaseModel):
    amount: int = Field(ge=10, le=10000)

class CouponIn(BaseModel):
    code: str = Field(max_length=20)
    amount: float = Field(gt=0, le=1000000)
    scope: Literal["ride", "parcel", "shop"] = "ride"

class StatusIn(BaseModel):
    status: str = Field(max_length=20)

class ActiveIn(BaseModel):
    active: bool

class VehicleIn(BaseModel):
    plate: str = Field(min_length=3, max_length=20)
    type: str = Field(min_length=2, max_length=40)
    capacity_kg: float = Field(gt=0, le=50000)
    lat: float = 26.9124
    lng: float = 75.7873
    documents: str = "Pending"
    next_maintenance: str = ""
    cost_per_km: float = Field(10, gt=0, le=1000)

class DriverIn(BaseModel):
    user_id: int
    license: str = Field(min_length=4, max_length=40)
    vehicle_id: Optional[int] = None
    lat: float = 26.9124
    lng: float = 75.7873
    documents: str = "Pending"

class AlertIn(BaseModel):
    event: str = Field(max_length=40)
    entity_type: str = Field(max_length=40)
    entity_id: int
    message: str = Field("Operational event", max_length=300)

class OptimizerIn(BaseModel):
    order_ids: list[int] = []
    vehicle_ids: list[int] = []
    traffic_factor: float = Field(1.0, ge=0.8, le=2.5)
    strategy: str = "balanced"
    apply: bool = True            # False = preview only, nothing is saved
    use_roads: bool = True        # real road distances (OSRM) when online
    time_limit_s: float = Field(1.5, ge=0.2, le=5.0)


class ChatIn(BaseModel):
    message: str = Field(max_length=500)
    history: list[dict] = Field(default_factory=list, max_length=12)

class ActionIn(BaseModel):
    id: int
