import time

RIDE = {"pickup": "A", "pickup_lat": 26.9, "pickup_lng": 75.8, "dropoff": "B", "drop_lat": 26.82, "drop_lng": 75.81}


def place(client, h, qty=1):
    r = client.post("/api/orders", headers=h, json={"address_id": 1, "priority": 3, "delivery_window": "Today 08:00-22:00", "items": [{"item_id": 1, "quantity": qty}]}); assert r.status_code == 200
    return r.json()["id"]


def test_estimate_falls_back_to_formula_without_models(client, auth):
    r = client.post("/api/rides/estimate", headers=auth("c1@test.in"), json=RIDE).json()
    assert r["eta_source"] == "formula" and r["weather"]["rain"] is False and all(o["factors"] == [] for o in r["options"])


def test_estimate_uses_ml_eta_and_explains_it(client, auth, use_models):
    r = client.post("/api/rides/estimate", headers=auth("c1@test.in"), json=RIDE).json()
    assert r["eta_source"] == "ml" and all(o["eta_min"] >= 3 for o in r["options"]) and all(isinstance(o["factors"], list) for o in r["options"])


def test_booking_stores_the_ml_eta(client, auth, use_models, sql):
    r = client.post("/api/rides", headers=auth("c1@test.in"), json=RIDE).json()
    est = client.post("/api/rides/estimate", headers=auth("c2@test.in"), json=RIDE).json()["options"][2]["eta_min"]
    assert abs(sql("SELECT eta_min FROM rides WHERE id=?", (r["id"],))[0][0] - est) <= 2


def test_optimizer_adds_delay_risk_per_stop_and_saves_it(client, auth, use_models, sql):
    hc, hd = auth("c1@test.in"), auth("disp@test.in"); place(client, hc); place(client, hc)
    pv = client.post("/api/optimizer/run", headers=hd, json={"apply": False}).json()
    stops = pv["routes"][0]["stop_details"]; assert pv["risk_source"] == "ml"
    assert all(0 <= s["delay_risk"] <= 1 and s["risk_level"] in ("low", "medium", "high") for s in stops) and "high_risk_stops" in pv["routes"][0]
    ap = client.post("/api/optimizer/run", headers=hd, json={}).json()
    saved = sql("SELECT delay_risk FROM route_orders")[0][0]; assert saved is not None and abs(saved - ap["routes"][0]["stop_details"][0]["delay_risk"]) < 1e-6


def test_optimizer_risk_uses_heuristic_without_models(client, auth):
    hc, hd = auth("c1@test.in"), auth("disp@test.in"); place(client, hc)
    assert client.post("/api/optimizer/run", headers=hd, json={"apply": False}).json()["risk_source"] == "heuristic"


def test_ml_dashboard_and_permissions(client, auth, use_models):
    a = client.get("/api/ml/predictions", headers=auth("admin@test.in")).json()
    assert a["status"]["models"] == {"eta": True, "delay": True, "demand": True} and len(a["forecast"]["labels"]) == 24 and a["report"]["models"]["eta"]["metrics"]["mae_min"] > 0
    assert len(a["hotspots"]) == 5 and "weather" in a and "route_performance_score" in a
    assert client.get("/api/ml/predictions", headers=auth("c1@test.in")).status_code == 403
    assert client.post("/api/ml/retrain", headers=auth("disp@test.in")).status_code == 403


def test_driver_can_see_hotspots(client, auth, use_models):
    r = client.get("/api/ml/hotspots", headers=auth("d1@test.in")).json(); assert len(r["zones"]) == 3 and r["source"] == "ml"
    assert client.get("/api/ml/hotspots", headers=auth("c1@test.in")).status_code == 403


def test_admin_retrain_runs_in_background(client, auth, ml_trained, tmp_path):
    from services import mlserve
    mlserve.ART = tmp_path / "fresh"
    assert client.post("/api/ml/retrain", headers=auth("admin@test.in")).json() == {"started": True}
    assert client.post("/api/ml/retrain", headers=auth("admin@test.in")).status_code == 409
    for _ in range(120):
        if not mlserve._state["training"]: break
        time.sleep(0.5)
    st = client.get("/api/ml/status", headers=auth("admin@test.in")).json()
    assert st["training"] is False and st["models"]["eta"] is True and st["error"] is None
