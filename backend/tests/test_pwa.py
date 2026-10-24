import os, sys, pathlib, json
ROOT = pathlib.Path(__file__).parents[2]
sys.path.insert(0, str(ROOT / "backend"))
os.environ.setdefault("ROUTENEX_DB", str(ROOT / "database" / "test.db")); os.environ.setdefault("ROUTENEX_SECRET", "test-secret-value")
from fastapi.testclient import TestClient
import app as appmod

client = TestClient(appmod.app)


def test_manifest_is_installable():
    r = client.get("/manifest.webmanifest"); assert r.status_code == 200 and "manifest+json" in r.headers["content-type"]
    m = r.json(); assert m["display"] == "standalone" and m["start_url"] == "/"
    sizes = {i["sizes"] for i in m["icons"]}; assert {"192x192", "512x512"} <= sizes
    for i in m["icons"]: assert client.get(i["src"]).status_code == 200      # every icon is really served


def test_service_worker_served_from_root_scope():
    r = client.get("/sw.js"); assert r.status_code == 200 and "javascript" in r.headers["content-type"]
    assert r.headers["service-worker-allowed"] == "/" and "fetch" in r.text


def test_page_has_csp_and_pwa_links():
    r = client.get("/"); csp = r.headers["content-security-policy"]
    assert "script-src 'self' https://unpkg.com" in csp and "'unsafe-inline'" not in csp.split("style-src")[0]
    assert 'rel="manifest"' in r.text and "/static/pwa.js" in r.text


def test_app_js_has_no_inline_handlers_and_escapes_data():
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert 'onclick="' not in js and "const esc=" in js
