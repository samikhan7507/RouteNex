def close_route_if_done(c, route_id):
    """When every order on a route is finished, complete the route and free its vehicle + driver."""
    r = c.execute("SELECT * FROM routes WHERE id=?", (route_id,)).fetchone()
    if not r or r["status"] not in ("planned", "active"):
        return
    left = c.execute("SELECT COUNT(*) FROM orders WHERE route_id=? AND status NOT IN ('delivered','failed','cancelled')", (route_id,)).fetchone()[0]
    if left == 0:
        c.execute("UPDATE routes SET status='completed' WHERE id=?", (route_id,))
        c.execute("UPDATE vehicles SET available=1,status='available' WHERE id=? AND status='assigned'", (r["vehicle_id"],))
        c.execute("UPDATE drivers SET available=1,status='available' WHERE id=? AND status='assigned'", (r["driver_id"],))
