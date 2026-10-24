from fastapi import APIRouter, Depends, HTTPException
from db import rows, one, run, tx, audit
from deps import current, roles, driver_of
from schemas import Address, OrderIn, StatusIn
from services.lifecycle import close_route_if_done
from services import trips

router = APIRouter(prefix="/api", tags=["shop"])

ORDER_Q = """SELECT o.*,a.label address_label,a.line1,(SELECT json_group_array(json_object('name',i.name,'quantity',oi.quantity)) FROM order_items oi JOIN items i ON i.id=oi.item_id WHERE oi.order_id=o.id) items FROM orders o LEFT JOIN addresses a ON a.id=o.address_id"""
# driver may move an order forward only along these edges; 'assigned' is set by the optimizer only
ORDER_FLOW = {"assigned": {"picked_up", "in_transit", "failed"}, "picked_up": {"in_transit", "delivered", "failed"}, "in_transit": {"delivered", "failed"}}
CUSTOMER_CANCELLABLE = {"placed", "pending", "assigned"}


@router.get("/items")
def items():
    return rows("SELECT * FROM items WHERE active=1 ORDER BY id")


@router.get("/addresses")
def addresses(u=Depends(current)):
    return rows("SELECT * FROM addresses WHERE user_id=?", (u["id"],))


@router.post("/addresses")
def add_address(x: Address, u=Depends(current)):
    i = run("INSERT INTO addresses(user_id,label,line1,city,state,pincode,lat,lng) VALUES(?,?,?,?,?,?,?,?)",
            (u["id"], x.label, x.line1, x.city, x.state, x.pincode, x.lat, x.lng))
    audit(u["id"], "CREATE", "address", i)
    return one("SELECT * FROM addresses WHERE id=?", (i,))


@router.get("/orders")
def orders(u=Depends(current)):
    if u["role"] == "customer":
        return rows(ORDER_Q + " WHERE o.user_id=? ORDER BY o.id DESC LIMIT 500", (u["id"],))
    if u["role"] == "driver":
        d = driver_of(u)
        if not d:
            return []
        return rows(ORDER_Q + " WHERE o.route_id IN (SELECT id FROM routes WHERE driver_id=?) ORDER BY o.id DESC LIMIT 500", (d["id"],))
    return rows(ORDER_Q + " ORDER BY o.id DESC LIMIT 500")


@router.post("/orders")
def create_order(x: OrderIn, u=Depends(roles("customer", "admin"))):
    a = one("SELECT * FROM addresses WHERE id=? AND user_id=?", (x.address_id, u["id"]))
    if not a:
        raise HTTPException(404, "Address not found")
    merged = {}
    for z in x.items:                       # same item twice in a cart -> one line
        merged[z.item_id] = merged.get(z.item_id, 0) + z.quantity
    with tx() as c:                         # stock check + decrement + order insert are ONE atomic unit
        total, weight, lines = 0.0, 0.0, []
        for item_id, q in merged.items():
            it = c.execute("SELECT * FROM items WHERE id=? AND active=1", (item_id,)).fetchone()
            if not it:
                raise HTTPException(400, f"Item {item_id} is not available")
            if c.execute("UPDATE items SET stock=stock-? WHERE id=? AND stock>=?", (q, item_id, q)).rowcount != 1:
                raise HTTPException(409, f"Only {it['stock']} left of {it['name']}")
            total += it["price"] * q
            weight += (it["weight_kg"] if it["weight_kg"] is not None else 2.0) * q
            lines.append((it["id"], q, it["price"]))
        subtotal = round(total, 2)
        discount, code = trips.evaluate_coupon(c, u["id"], x.coupon, subtotal, "shop")
        total = round(subtotal - discount, 2)
        oid = c.execute("INSERT INTO orders(user_id,address_id,priority,delivery_window,total,lat,lng,discount,payment_method,coupon,weight_kg) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                        (u["id"], x.address_id, x.priority, x.delivery_window, total, a["lat"], a["lng"], discount, x.payment_method, code, round(weight, 2))).lastrowid
        pstatus, prepaid = trips.charge(c, u["id"], total, x.payment_method, "order", oid)
        c.execute("UPDATE orders SET payment_status=?,paid_amount=? WHERE id=?", (pstatus, prepaid, oid))
        trips.record_coupon_use(c, code, u["id"], "order", oid)
        for item_id, q, price in lines:
            c.execute("INSERT INTO order_items(order_id,item_id,quantity,unit_price) VALUES(?,?,?,?)", (oid, item_id, q, price))
    audit(u["id"], "CREATE", "order", oid, f"total={total}")
    return {"id": oid, "status": "placed", "total": total, "discount": discount, "payment_status": pstatus}


@router.patch("/orders/{oid}/cancel")
def cancel(oid: int, u=Depends(current)):
    if u["role"] in ("driver", "fleet_manager"):
        raise HTTPException(403, "Insufficient permission")
    with tx() as c:
        o = c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        if not o or (u["role"] == "customer" and o["user_id"] != u["id"]):
            raise HTTPException(404, "Order not found")
        if o["status"] in ("delivered", "cancelled", "failed"):
            raise HTTPException(409, "Order cannot be cancelled")
        if u["role"] == "customer" and o["status"] not in CUSTOMER_CANCELLABLE:
            raise HTTPException(409, "Order is already on its way and can no longer be cancelled")
        for li in c.execute("SELECT item_id,quantity FROM order_items WHERE order_id=?", (oid,)).fetchall():
            c.execute("UPDATE items SET stock=stock+? WHERE id=?", (li["quantity"], li["item_id"]))
        c.execute("UPDATE orders SET status='cancelled',route_id=NULL,payment_status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", ("refunded" if (o["paid_amount"] or 0) > 0 else "cancelled", oid))
        trips.refund_to_wallet(c, o["user_id"], o["paid_amount"] or 0, "order", oid, f"Refund for cancelled order #{oid}")
        c.execute("DELETE FROM coupon_uses WHERE ref_type='order' AND ref_id=?", (oid,))
        c.execute("DELETE FROM route_orders WHERE order_id=?", (oid,))
        if o["route_id"]:
            close_route_if_done(c, o["route_id"])
        c.execute("INSERT INTO alerts(type,severity,message,entity_type,entity_id) VALUES('cancellation','medium',?,'order',?)",
                  (f"Order #{oid} cancelled; re-optimization needed", oid))
    audit(u["id"], "CANCEL", "order", oid)
    return {"status": "cancelled", "reroute_required": True}


@router.patch("/orders/{oid}/status")
def order_status(oid: int, x: StatusIn, u=Depends(roles("driver", "dispatcher", "admin"))):
    with tx() as c:
        o = c.execute("SELECT * FROM orders WHERE id=?", (oid,)).fetchone()
        if not o:
            raise HTTPException(404, "Order not found")
        if u["role"] == "driver":
            d = driver_of(u)
            owns = d and o["route_id"] and c.execute("SELECT 1 FROM routes WHERE id=? AND driver_id=?", (o["route_id"], d["id"])).fetchone()
            if not owns:
                raise HTTPException(403, "This order is not on your route")
        if x.status not in ORDER_FLOW.get(o["status"], set()):
            raise HTTPException(409, f"Cannot move order from {o['status']} to {x.status}")
        c.execute("UPDATE orders SET status=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (x.status, oid))
        if o["route_id"]:
            if x.status == "picked_up":
                c.execute("UPDATE routes SET status='active' WHERE id=? AND status='planned'", (o["route_id"],))
            if x.status in ("delivered", "failed"):
                close_route_if_done(c, o["route_id"])
    audit(u["id"], "STATUS", "order", oid, x.status)
    return {"id": oid, "status": x.status}
