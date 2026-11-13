"""Immutable route previews and atomic, snapshot-checked application.

The optimizer is a deterministic capacitated insertion/local-search heuristic.
Distances are explicitly labelled estimates. Applying a preview NEVER re-solves:
it persists the exact sequences the dispatcher reviewed, or rejects stale input.
"""
from __future__ import annotations
import hashlib
import json
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Driver, Order, Route, RoutePlan, RouteStop, User, Vehicle, utcnow
from app.services import vrp
from app.services.common import audit, notify
from app.services.geo import matrix
from app.services.pricing import IST

DISPATCH_LOCK = 742001


def clock(minutes: int) -> str:
    m = int(round(minutes)) % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def eligible(db: Session):
    orders = list(db.scalars(select(Order).where(Order.status == "placed", Order.route_id.is_(None)).order_by(Order.id).with_for_update()))
    now_ist = utcnow().astimezone(IST)
    orders = [o for o in orders if o.delivery_window_start.astimezone(IST).date() <= now_ist.date() and o.delivery_window_end > utcnow()]
    vehicles = list(db.scalars(select(Vehicle).where(Vehicle.status == "available", Vehicle.lat.is_not(None)).order_by(Vehicle.id).with_for_update()))
    drivers = list(db.scalars(select(Driver).join(User).where(Driver.status == "available", Driver.online.is_(True),
                     Driver.service.in_(["delivery", "both"]), Driver.documents == "Verified", User.active.is_(True)).order_by(Driver.id).with_for_update()))
    # One driver per vehicle per plan. Duplicate links are reported, not double-booked.
    chosen, seen, duplicates = [], set(), []
    for d in drivers:
        if d.vehicle_id in seen:
            duplicates.append({"driver_id": d.id, "vehicle_id": d.vehicle_id, "reason": "Vehicle already has an eligible driver in this plan"})
            continue
        if d.vehicle_id and any(v.id == d.vehicle_id for v in vehicles):
            chosen.append(d)
            seen.add(d.vehicle_id)
    fleet = [v for v in vehicles if v.id in seen]
    return orders, fleet, chosen, duplicates


def snapshot(orders, fleet, drivers) -> str:
    state = {"orders": [[o.id, o.status, o.updated_at.isoformat(), o.weight_grams, o.priority,
                         o.delivery_window_start.isoformat(), o.delivery_window_end.isoformat()] for o in orders],
             "vehicles": [[v.id, v.status, v.updated_at.isoformat()] for v in fleet],
             "drivers": [[d.id, d.status, d.vehicle_id, d.online, d.updated_at.isoformat()] for d in drivers]}
    return hashlib.sha256(json.dumps(state, sort_keys=True).encode()).hexdigest()


def _minutes(value):
    local = value.astimezone(IST)
    return local.hour * 60 + local.minute


def preview(db: Session, user: User, config: dict) -> dict:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": DISPATCH_LOCK})
    orders, fleet, drivers, duplicates = eligible(db)
    if not orders:
        raise HTTPException(409, "No unassigned, paid/confirmed orders are ready for dispatch")
    if not fleet:
        raise HTTPException(409, "No available vehicle has an online, verified delivery driver")
    now = utcnow()
    start = _minutes(now.astimezone(IST)) + 10
    points = [(float(v.lat), float(v.lng)) for v in fleet] + [(float(o.address.lat), float(o.address.lng)) for o in orders]
    D = matrix(points)
    problem_orders = [{"id": o.id, "weight": o.weight_grams / 1000, "priority": o.priority,
                       "win": (max(start, _minutes(o.delivery_window_start)), max(start + 1, _minutes(o.delivery_window_end))),
                       "svc": vrp.service_minutes(o.weight_grams / 1000)} for o in orders]
    problem_vehicles = [{"id": v.id, "type": v.type, "cap": float(v.capacity_kg), "cpk": v.cost_per_km_paise / 100} for v in fleet]
    problem = vrp.build_problem(problem_orders, problem_vehicles, D, start, config["traffic_factor"])
    sequences, left, reasons = problem.solve(time_limit=config["time_limit_seconds"])
    baseline_routes, baseline_left = problem.baseline()
    before, after = problem.metrics(baseline_routes, baseline_left), problem.metrics(sequences, left)
    plans = []
    for k, seq in enumerate(sequences):
        if not seq:
            continue
        run = problem.run(k, seq)
        v = fleet[k]
        d = next(x for x in drivers if x.vehicle_id == v.id)
        stops = []
        previous = k
        for position, (j, arrival) in enumerate(zip(seq, run["arr"]), 1):
            o = orders[j]
            leg = D[previous][len(fleet) + j]
            stops.append({"order_id": o.id, "sequence": position, "eta": clock(arrival[0]),
                          "arrival_min": arrival[0], "leg_km": round(leg, 2), "lat": float(o.address.lat), "lng": float(o.address.lng),
                          "priority": o.priority, "window_end": _minutes(o.delivery_window_end)})
            previous = len(fleet) + j
        plans.append({"vehicle_id": v.id, "driver_id": d.id, "vehicle_plate": v.plate, "driver_name": d.user.name,
                      "distance_km": round(run["dist"], 2), "duration_min": round(run["dur"]),
                      "cost_paise": round(run["cost"] * 100), "load_kg": round(run["load"], 2),
                      "geometry": [[float(v.lat), float(v.lng)]] + [[float(orders[j].address.lat), float(orders[j].address.lng)] for j in seq],
                      "stops": stops})
    result = {"routes": plans, "unassigned": [{"order_id": orders[j].id, "reason": reasons[j]} for j in left],
              "excluded_drivers": duplicates, "before": before, "after": after,
              "distance_saved_pct": vrp.pct(before["distance_km"], after["distance_km"]),
              "objective_saved_pct": vrp.pct(before["objective"], after["objective"]),
              "distance_source": "estimate", "algorithm": "priority insertion + 2-opt/relocate/swap"}
    plan = RoutePlan(created_by=user.id, config=config, result=result, state_hash=snapshot(orders, fleet, drivers),
                     expires_at=now + timedelta(minutes=10))
    db.add(plan)
    db.flush()
    audit(db, user, "ROUTE_PREVIEW", "route_plan", plan.id, {"orders": len(orders), "routes": len(plans)})
    return {"plan_id": plan.id, "expires_at": plan.expires_at, "state_hash": plan.state_hash, **result}


def apply(db: Session, user: User, plan_id: str) -> dict:
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": DISPATCH_LOCK})
    plan = db.scalar(select(RoutePlan).where(RoutePlan.id == plan_id).with_for_update())
    if not plan or (plan.created_by != user.id and user.role != "admin"):
        raise HTTPException(404, "Route preview not found")
    if plan.status != "preview" or plan.expires_at <= utcnow():
        raise HTTPException(409, "This preview was already used or has expired. Generate a new preview")
    orders, fleet, drivers, _ = eligible(db)
    if snapshot(orders, fleet, drivers) != plan.state_hash:
        plan.status = "rejected"
        raise HTTPException(409, "Orders, drivers or vehicles changed after this preview. Review a new plan before applying")
    created = []
    for entry in plan.result["routes"]:
        route = Route(plan_id=plan.id, vehicle_id=entry["vehicle_id"], driver_id=entry["driver_id"],
                      distance_km=entry["distance_km"], duration_min=entry["duration_min"], cost_paise=entry["cost_paise"],
                      load_kg=entry["load_kg"], geometry=entry["geometry"], reason="Dispatcher-approved immutable preview")
        db.add(route)
        db.flush()
        for stop in entry["stops"]:
            order = next(o for o in orders if o.id == stop["order_id"])
            order.status, order.route_id = "assigned", route.id
            db.add(RouteStop(route_id=route.id, order_id=order.id, sequence=stop["sequence"], eta=stop["eta"], arrival_min=stop["arrival_min"]))
            notify(db, order.user_id, "Delivery scheduled", f"Order #{order.id} is assigned for delivery. Estimated stop time: {stop['eta']}.")
        vehicle = db.get(Vehicle, entry["vehicle_id"])
        driver = db.get(Driver, entry["driver_id"])
        vehicle.status, driver.status = "assigned", "assigned"
        created.append(route.id)
    plan.status, plan.applied_at = "applied", utcnow()
    db.flush()
    audit(db, user, "ROUTE_APPLY", "route_plan", plan.id, {"routes": created, "exact_preview": True})
    return {"plan_id": plan.id, "route_ids": created, "exact_preview": True}


def release_route(db: Session, route: Route, reason: str):
    """Release unfinished work atomically; completed history stays attached."""
    unfinished = list(db.scalars(select(Order).where(Order.route_id == route.id, Order.status.in_(["assigned", "picked_up", "out_for_delivery"])).with_for_update()))
    for order in unfinished:
        order.status, order.route_id = "placed", None
        notify(db, order.user_id, "Delivery being reassigned", reason)
    route.status, route.reason = "reroute_required", reason
    if not db.scalar(select(Order.id).where(Order.route_id == route.id, Order.status.in_(["assigned", "picked_up", "out_for_delivery"])).limit(1)):
        route.vehicle.status = "available"
        route.driver.status = "available" if route.driver.online else "offline"
    return len(unfinished)


def close_route_if_done(db: Session, route_id: int | None):
    if not route_id:
        return
    route = db.scalar(select(Route).where(Route.id == route_id).with_for_update())
    active = db.scalar(select(Order.id).where(Order.route_id == route_id, Order.status.in_(["assigned", "picked_up", "out_for_delivery"])).limit(1))
    if not active and route.status in ("planned", "active"):
        route.status = "completed"
        route.vehicle.status = "available"
        route.driver.status = "available" if route.driver.online else "offline"
