import json
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from db import rows, one, run, tx, audit
from deps import roles, current, driver_of
from schemas import OptimizerIn, AlertIn, ActiveIn
from services.errors import ApiError
from services.pricing import IST
from services.roads import matrix as road_matrix
from services.vrp import build_problem, service_minutes, pct
from services.windows import parse_window, clock
from services import mlserve

router = APIRouter(prefix="/api", tags=["operations"])
OPS = ("dispatcher", "fleet_manager", "admin")


HORIZON_MIN = 120   # orders whose delivery window opens later than this are left for a later plan


def _now_ist():
    """Planner clock in IST. A function so tests can pin the time (the optimizer's behaviour depends on the time of day)."""
    return datetime.now(IST)


def plan_and_apply(cfg: OptimizerIn, u):
    """Read -> solve (no DB lock held while we wait for road distances) -> optionally write routes in one transaction."""
    pending = rows("""SELECT id,priority,delivery_window,lat,lng,COALESCE(weight_kg,5) weight_kg FROM orders
                      WHERE status IN ('placed','pending') AND lat IS NOT NULL ORDER BY priority DESC,created_at""")
    fleet = rows("""SELECT v.id,v.plate,v.type,v.capacity_kg,v.cost_per_km,v.lat,v.lng,d.id driver_id FROM vehicles v JOIN drivers d ON d.vehicle_id=v.id
                    WHERE v.available=1 AND v.status='available' AND d.available=1 AND d.status='available' AND d.online=1
                    AND d.service IN ('delivery','both') AND v.lat IS NOT NULL""")
    if cfg.order_ids:
        pending = [o for o in pending if o["id"] in cfg.order_ids]
    if cfg.vehicle_ids:
        fleet = [v for v in fleet if v["id"] in cfg.vehicle_ids]
    if not pending:
        return {"routes": [], "unassigned": [], "excluded": [], "applied": False, "message": "No pending orders"}
    if not fleet:
        raise ApiError(409, "No available vehicle/driver pairs")
    now = _now_ist()
    start = now.hour * 60 + now.minute
    orders, excluded = [], []
    for o in pending:
        e, l = parse_window(o["delivery_window"])
        if l <= start:                       # window already passed -> serve as soon as possible
            e, l = start, start + 90
        elif e > start + HORIZON_MIN:
            excluded.append({"order_id": o["id"], "reason": f"Window opens at {clock(e)} - planned later"})
            continue
        orders.append({"id": o["id"], "weight": float(o["weight_kg"]), "priority": int(o["priority"]), "win": (e, l), "svc": service_minutes(float(o["weight_kg"])),
                       "lat": o["lat"], "lng": o["lng"]})
    if not orders:
        return {"routes": [], "unassigned": [], "excluded": excluded, "applied": False, "message": "Nothing to plan right now"}
    D, source = road_matrix([(v["lat"], v["lng"]) for v in fleet] + [(o["lat"], o["lng"]) for o in orders], cfg.use_roads)
    P = build_problem(orders, [{"id": v["id"], "type": v["type"], "cap": v["capacity_kg"], "cpk": v["cost_per_km"]} for v in fleet], D, start, cfg.traffic_factor)
    routes, left, reasons = P.solve(cfg.time_limit_s)
    m_opt, m_base = P.metrics(routes, left), P.metrics(*P.baseline())
    out_routes = []
    for k, seq in enumerate(routes):
        if not seq:
            continue
        v, r = fleet[k], P.run(k, seq)
        stops = [{"order_id": orders[j]["id"], "sequence": n, "arrive": clock(arr), "arrive_min": arr, "wait_min": wait, "late_min": late,
                  "window": f"{clock(orders[j]['win'][0])}-{clock(orders[j]['win'][1])}", "weight_kg": orders[j]["weight"], "priority": orders[j]["priority"],
                  "lat": orders[j]["lat"], "lng": orders[j]["lng"]} for n, (j, (arr, wait, late)) in enumerate(zip(seq, r["arr"]), 1)]
        out_routes.append({"route_id": None, "vehicle": v["plate"], "vehicle_type": v["type"], "vehicle_id": v["id"], "driver_id": v["driver_id"],
                           "orders": [orders[j]["id"] for j in seq], "stops": len(seq), "stop_details": stops, "distance_km": round(r["dist"], 2),
                           "duration_min": round(r["dur"]), "cost": round(r["dist"] * v["cost_per_km"], 2), "load_kg": round(r["load"], 1),
                           "capacity_kg": v["capacity_kg"], "capacity_utilization": round(min(100.0, r["load"] / v["capacity_kg"] * 100), 1),
                           "depot": [v["lat"], v["lng"]], "estimated_savings": 0.0})
    # ML delay risk for every planned stop (trained model; heuristic fallback)
    flat, owners = [], []
    for k, seq in enumerate(routes):
        if not seq:
            continue
        rr = next(x for x in out_routes if x["vehicle_id"] == fleet[k]["id"]); prev = k
        for n, (j, st) in enumerate(zip(seq, rr["stop_details"]), 1):
            flat.append({"slack": orders[j]["win"][1] - st["arrive_min"], "seq": n, "n_stops": len(seq), "leg_km": D[prev][len(fleet) + j], "route_km": rr["distance_km"],
                         "load_ratio": rr["load_kg"] / max(1.0, rr["capacity_kg"]), "hour": st["arrive_min"] // 60, "priority": orders[j]["priority"], "vtype": fleet[k]["type"],
                         "lat": orders[j]["lat"], "lng": orders[j]["lng"]})
            owners.append(st); prev = len(fleet) + j
    risks, risk_src = mlserve.delay_risks(flat)
    for st, rk in zip(owners, risks):
        st["delay_risk"], st["risk_level"], st["risk_factors"] = rk["risk"], rk["level"], rk["factors"]
    for rr in out_routes:
        rr["high_risk_stops"] = sum(1 for s in rr["stop_details"] if s.get("risk_level") == "high")
    total_km = sum(r["distance_km"] for r in out_routes) or 1.0
    saving = max(0.0, m_base["travel_cost"] - m_opt["travel_cost"])
    for r in out_routes:
        r["estimated_savings"] = round(saving * r["distance_km"] / total_km, 2)
    unassigned = [{"order_id": orders[j]["id"], "reason": reasons[j]} for j in left]
    result = {"routes": out_routes, "unassigned": [x["order_id"] for x in unassigned], "unassigned_detail": unassigned, "excluded": excluded,
              "applied": False, "distance_source": source, "method": "vrp-v1", "risk_source": risk_src,
              "metrics": {"baseline": m_base, "optimized": m_opt,
                          "improvement": {"distance_pct": pct(m_base["distance_km"], m_opt["distance_km"]), "cost_pct": pct(m_base["travel_cost"], m_opt["travel_cost"]),
                                          "late_minutes_saved": m_base["late_minutes"] - m_opt["late_minutes"], "objective_pct": pct(m_base["objective"], m_opt["objective"])}},
              "objective": "minimize distance cost + lateness + unassigned penalties under capacity and shift limits"}
    if not cfg.apply:
        return result
    with tx() as c:
        for r in out_routes:
            geometry = [r["depot"]] + [[s["lat"], s["lng"]] for s in r["stop_details"]]
            rid = c.execute("INSERT INTO routes(vehicle_id,driver_id,distance_km,duration_min,cost,geometry,reason,load_kg,method,saved_km) VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (r["vehicle_id"], r["driver_id"], r["distance_km"], r["duration_min"], r["cost"], json.dumps(geometry),
                             f"VRP: capacity + time windows + priority ({source} distances)", r["load_kg"], "vrp-v1", 0)).lastrowid
            r["route_id"] = rid
            for s in r["stop_details"]:
                c.execute("INSERT OR REPLACE INTO route_orders(route_id,order_id,stop_sequence,eta,arrival_min,delay_risk) VALUES(?,?,?,?,?,?)", (rid, s["order_id"], s["sequence"], s["arrive"], s["arrive_min"], s.get("delay_risk")))
                c.execute("UPDATE orders SET route_id=?,status='assigned',updated_at=CURRENT_TIMESTAMP WHERE id=?", (rid, s["order_id"]))
            c.execute("UPDATE vehicles SET available=0,status='assigned' WHERE id=?", (r["vehicle_id"],))
            c.execute("UPDATE drivers SET available=0,status='assigned' WHERE id=?", (r["driver_id"],))
        for x in unassigned:
            c.execute("INSERT INTO alerts(type,severity,message,entity_type,entity_id) VALUES('capacity','high',?,'order',?)", (f"Order #{x['order_id']} not planned: {x['reason']}", x["order_id"]))
    result["applied"] = True
    audit(u["id"], "RUN", "optimizer", "batch", f"{len(out_routes)} routes, {len(unassigned)} unassigned")
    return result


@router.get("/optimizer/overview")
def optimizer_overview(u=Depends(roles(*OPS))):
    """Counts on the Optimizer page: orders waiting and vehicles the optimizer can actually use (delivery-capable, free driver, online)."""
    pend = one("SELECT COUNT(*) n FROM orders WHERE status IN ('placed','pending') AND lat IS NOT NULL")["n"]
    fleet = one("""SELECT COUNT(*) n FROM vehicles v JOIN drivers d ON d.vehicle_id=v.id WHERE v.available=1 AND v.status='available'
                   AND d.available=1 AND d.status='available' AND d.online=1 AND d.service IN ('delivery','both') AND v.lat IS NOT NULL""")["n"]
    return {"pending": pend, "vehicles": fleet}


@router.post("/optimizer/run")
def optimize(cfg: Optional[OptimizerIn] = None, u=Depends(roles(*OPS))):
    return plan_and_apply(cfg or OptimizerIn(), u)


@router.get("/routes")
def route_list(u=Depends(roles("driver", *OPS))):
    q = """SELECT r.*,v.plate,u.name driver_name,(SELECT json_group_array(json_object('order_id',ro.order_id,'sequence',ro.stop_sequence,'eta',ro.eta)) FROM route_orders ro WHERE ro.route_id=r.id) stops
           FROM routes r LEFT JOIN vehicles v ON v.id=r.vehicle_id LEFT JOIN drivers d ON d.id=r.driver_id LEFT JOIN users u ON u.id=d.user_id"""
    if u["role"] == "driver":
        d = driver_of(u)
        return rows(q + " WHERE r.driver_id=? ORDER BY r.id DESC LIMIT 200", (d["id"],)) if d else []
    return rows(q + " ORDER BY r.id DESC LIMIT 200")


@router.post("/reroute")
def reroute(x: AlertIn, u=Depends(roles(*OPS))):
    affected = []
    with tx() as c:
        aid = c.execute("INSERT INTO alerts(type,severity,message,entity_type,entity_id) VALUES(?,?,?,?,?)",
                        (x.event, "high", x.message, x.entity_type, x.entity_id)).lastrowid
        if x.entity_type == "vehicle" and x.event in ("failure", "breakdown"):
            if not c.execute("SELECT 1 FROM vehicles WHERE id=?", (x.entity_id,)).fetchone():
                raise ApiError(404, "Vehicle not found")
            c.execute("UPDATE vehicles SET status='breakdown',available=0 WHERE id=?", (x.entity_id,))
            for r in c.execute("SELECT id FROM routes WHERE vehicle_id=? AND status IN ('planned','active')", (x.entity_id,)).fetchall():
                c.execute("UPDATE routes SET status='reroute_required',reason=? WHERE id=?", (x.message, r["id"]))
                c.execute("UPDATE orders SET status='pending',route_id=NULL WHERE route_id=? AND status NOT IN ('delivered','failed','cancelled')", (r["id"],))
                affected.append(r["id"])
    audit(u["id"], "REROUTE", x.entity_type, x.entity_id, x.event)
    replanned = None
    if affected:                                   # dynamic rerouting: re-plan the released orders straight away
        try:
            replanned = plan_and_apply(OptimizerIn(), u)
        except ApiError as e:
            replanned = {"routes": [], "message": e.detail}
    return {"alert_id": aid, "affected_routes": affected, "action": "orders released and re-planned" if replanned and replanned.get("routes") else "orders released for reassignment",
            "reoptimized": replanned, "run_optimizer": bool(affected) and not (replanned and replanned.get("routes"))}


@router.get("/alerts")
def alerts(u=Depends(roles(*OPS))):
    return rows("SELECT * FROM alerts ORDER BY id DESC LIMIT 100")


@router.patch("/alerts/{aid}/ack")
def ack(aid: int, u=Depends(roles(*OPS))):
    if not one("SELECT 1 FROM alerts WHERE id=?", (aid,)):
        raise HTTPException(404, "Alert not found")
    run("UPDATE alerts SET acknowledged=1 WHERE id=?", (aid,))
    return {"acknowledged": True}


@router.get("/notifications")
def notifications(u=Depends(current)):
    return rows("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 100", (u["id"],))


@router.get("/audit")
def logs(u=Depends(roles("admin"))):
    return rows("SELECT a.*,u.name FROM audit_logs a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 200")


@router.get("/admin/users")
def users(u=Depends(roles("admin"))):
    return rows("SELECT id,name,email,phone,role,active,created_at FROM users ORDER BY id")


@router.patch("/admin/users/{uid}/active")
def set_active(uid: int, x: ActiveIn, u=Depends(roles("admin"))):
    if uid == u["id"]:
        raise HTTPException(400, "You cannot deactivate your own account")
    if not one("SELECT 1 FROM users WHERE id=?", (uid,)):
        raise HTTPException(404, "User not found")
    run("UPDATE users SET active=? WHERE id=?", (1 if x.active else 0, uid))
    audit(u["id"], "ACTIVE" if x.active else "DEACTIVATE", "user", uid)
    return {"id": uid, "active": x.active}


@router.get("/analytics/summary")
def analytics(u=Depends(roles(*OPS))):
    n = lambda sql: one(sql)["n"]
    k = {"users": n("SELECT COUNT(*) n FROM users"), "orders": n("SELECT COUNT(*) n FROM orders"), "rides": n("SELECT COUNT(*) n FROM rides"),
         "revenue": n("SELECT COALESCE(SUM(total),0) n FROM orders WHERE status!='cancelled'") + n("SELECT COALESCE(SUM(fare-COALESCE(discount,0)),0) n FROM rides WHERE status!='cancelled'"),
         "active_routes": n("SELECT COUNT(*) n FROM routes WHERE status IN ('planned','active')"),
         "available_vehicles": n("SELECT COUNT(*) n FROM vehicles WHERE available=1"),
         "alerts": n("SELECT COUNT(*) n FROM alerts WHERE acknowledged=0")}
    k["fleet_utilization"] = round(100 * (1 - k["available_vehicles"] / max(1, n("SELECT COUNT(*) n FROM vehicles"))), 1)
    k["operational_summary"] = f"{k['orders']} orders and {k['rides']} rides recorded. Fleet utilization is {k['fleet_utilization']}%. {k['alerts']} alerts need attention."
    return k
