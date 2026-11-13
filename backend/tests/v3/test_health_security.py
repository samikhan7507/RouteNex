def test_health_and_ready(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["version"] == "3.0.0"
    assert client.get("/api/ready").status_code == 200


def test_security_headers_and_request_id(client):
    r = client.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert "Content-Security-Policy" in r.headers
    assert r.headers["X-Request-ID"]
    assert r.headers["Cache-Control"] == "no-store"


def test_spa_fallback_and_api_404(client, tmp_path, monkeypatch):
    # API tests do not require ignored frontend build output; the web CI job tests the real SPA.
    from app import main

    (tmp_path / "index.html").write_text("<!doctype html><title>RouteNex</title><div id=root></div>")
    monkeypatch.setattr(main, "DIST", tmp_path)
    r = client.get("/shop")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "RouteNex" in r.text
    missing = client.get("/api/definitely-not-a-route")
    assert missing.status_code == 404
    assert "detail" in missing.json()


def test_unbuilt_spa_has_actionable_error(client, tmp_path, monkeypatch):
    from app import main

    monkeypatch.setattr(main, "DIST", tmp_path / "not-built")
    r = client.get("/shop")
    assert r.status_code == 503
    assert "npm run build" in r.json()["detail"]


def test_unauthenticated_mutation_is_rejected(client):
    r = client.post("/api/auth/logout")
    assert r.status_code == 401
