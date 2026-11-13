"""Explicit public representations; ORM objects and secret columns never leak implicitly."""
from app.core.config import get_settings
from app.core.security import reveal_code
from app.models import Driver, Order, Payment, Product, Route, Trip, User, Vehicle


def product(p: Product) -> dict:
    return {"id": p.id, "sku": p.sku, "name": p.name, "description": p.description, "category": p.category,
            "brand": p.brand, "unit": p.unit, "price": p.price_paise / 100, "price_paise": p.price_paise,
            "compare_at": p.compare_at_paise / 100 if p.compare_at_paise else None,
            "stock": p.stock, "available": max(0, p.stock - p.reserved), "weight_grams": p.weight_grams,
            "image": p.image_path, "image_credit": p.image_credit, "rating": float(p.rating),
            "review_count": p.review_count, "active": p.active}


def address(a) -> dict:
    return {"id": a.id, "label": a.label, "line1": a.line1, "city": a.city, "state": a.state,
            "pincode": a.pincode, "lat": float(a.lat), "lng": float(a.lng)}


def order(o: Order, viewer: User | None = None) -> dict:
    data = {"id": o.id, "user_id": o.user_id, "status": o.status, "priority": o.priority,
            "subtotal": o.subtotal_paise / 100, "discount": o.discount_paise / 100,
            "delivery_fee": o.delivery_fee_paise / 100, "total": o.total_paise / 100,
            "total_paise": o.total_paise, "payment_method": o.payment_method, "payment_status": o.payment_status,
            "coupon_code": o.coupon_code, "weight_kg": o.weight_grams / 1000, "route_id": o.route_id,
            "delivery_window_start": o.delivery_window_start, "delivery_window_end": o.delivery_window_end,
            "created_at": o.created_at, "updated_at": o.updated_at, "address": address(o.address),
            "items": [{"product_id": i.product_id, "name": i.product_name, "sku": i.sku, "quantity": i.quantity,
                       "unit_price": i.unit_price_paise / 100, "total": i.unit_price_paise * i.quantity / 100} for i in o.items]}
    if viewer and viewer.id == o.user_id and o.status not in ("cancelled", "failed"):
        data["delivery_otp"] = reveal_code(o.delivery_otp_encrypted)
    return data


def vehicle(v: Vehicle) -> dict:
    return {"id": v.id, "plate": v.plate, "type": v.type, "capacity_kg": float(v.capacity_kg),
            "cost_per_km": v.cost_per_km_paise / 100, "status": v.status, "lat": float(v.lat) if v.lat is not None else None,
            "lng": float(v.lng) if v.lng is not None else None, "documents": v.documents, "next_maintenance": v.next_maintenance}


def driver(d: Driver, private: bool = False) -> dict:
    data = {"id": d.id, "name": d.user.name, "service": d.service, "online": d.online, "status": d.status,
            "vehicle_id": d.vehicle_id, "vehicle": vehicle(d.vehicle) if d.vehicle else None,
            "rating": float(d.rating), "rating_count": d.rating_count,
            "lat": float(d.lat) if d.lat is not None else None, "lng": float(d.lng) if d.lng is not None else None}
    if private:
        data.update(user_id=d.user_id, email=d.user.email, phone=d.user.phone, license_number=d.license_number, documents=d.documents)
    return data


def trip(t: Trip, viewer: User | None = None) -> dict:
    data = {"id": t.id, "user_id": t.user_id, "kind": t.kind, "vehicle_class": t.vehicle_class, "status": t.status,
            "pickup": {"name": t.pickup_name, "lat": float(t.pickup_lat), "lng": float(t.pickup_lng)},
            "drop": {"name": t.drop_name, "lat": float(t.drop_lat), "lng": float(t.drop_lng)},
            "distance_km": float(t.distance_km), "fare": t.fare_paise / 100, "discount": t.discount_paise / 100,
            "total": t.total_paise / 100, "total_paise": t.total_paise, "eta_min": t.eta_min, "eta_source": t.eta_source,
            "payment_method": t.payment_method, "payment_status": t.payment_status, "coupon_code": t.coupon_code,
            "recipient_name": t.recipient_name, "recipient_phone": t.recipient_phone if viewer and viewer.id == t.user_id else None,
            "weight_kg": float(t.weight_kg) if t.weight_kg is not None else None, "parcel_size": t.parcel_size,
            "fragile": t.fragile, "description": t.description, "simulated": t.simulated,
            "created_at": t.created_at, "completed_at": t.completed_at, "cancelled_at": t.cancelled_at,
            "cancel_reason": t.cancel_reason, "rating": t.rating, "review": t.review,
            "driver": driver(t.driver) if t.driver else None}
    if viewer and viewer.id == t.user_id and t.status not in ("cancelled", "expired", "completed"):
        data["pickup_otp"] = reveal_code(t.pickup_otp_encrypted)
        if t.kind == "parcel":
            data["delivery_otp"] = reveal_code(t.delivery_otp_encrypted)
    if viewer and viewer.role == "driver" and t.driver and t.driver.user_id == viewer.id:
        data["recipient_phone"] = t.recipient_phone
        if get_settings().demo_mode and t.kind == "parcel":
            data["demo_delivery_otp"] = reveal_code(t.delivery_otp_encrypted)
    return data


def route(r: Route) -> dict:
    return {"id": r.id, "plan_id": r.plan_id, "vehicle_id": r.vehicle_id, "driver_id": r.driver_id,
            "vehicle": vehicle(r.vehicle), "driver": driver(r.driver), "status": r.status,
            "distance_km": float(r.distance_km), "duration_min": r.duration_min, "cost": r.cost_paise / 100,
            "load_kg": float(r.load_kg), "geometry": r.geometry, "reason": r.reason,
            "stops": [{"order_id": s.order_id, "sequence": s.sequence, "eta": s.eta,
                       "arrival_min": s.arrival_min, "delay_risk": float(s.delay_risk) if s.delay_risk is not None else None} for s in r.stops]}


def payment(p: Payment) -> dict:
    return {"id": p.public_id, "db_id": p.id, "purpose": p.purpose, "reference_id": p.reference_id,
            "provider": p.provider, "provider_payment_id": p.provider_payment_id, "amount": p.amount_paise / 100,
            "amount_paise": p.amount_paise, "currency": p.currency, "status": p.status, "method": p.method,
            "receipt": p.receipt, "failure_reason": p.failure_reason, "created_at": p.created_at, "captured_at": p.captured_at}
