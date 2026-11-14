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


def test_responsive_navigation_shell_is_accessible_and_cached():
    html = client.get('/').text
    assert 'id="navToggle"' in html and 'aria-controls="appSidebar"' in html
    assert 'aria-expanded="false"' in html and 'aria-label="Close menu"' in html
    assert 'aria-label="Refresh current page"' in html and 'aria-label="Sign out"' in html
    assert html.count('id="logout"') == 1 and 'id="logout2"' not in html
    assert html.index('id="logout"') < html.index('</aside>')
    assert html.index('/static/app.js') < html.index('/static/navigation.js')
    assert client.get('/static/navigation.js').status_code == 200
    assert '/static/navigation.js' in client.get('/sw.js').text


def test_versioned_assets_are_precached_and_revalidated():
    from html.parser import HTMLParser
    from urllib.parse import urlsplit

    class Assets(HTMLParser):
        def __init__(self):
            super().__init__()
            self.paths = []
        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            path = attrs.get('href') if tag == 'link' else attrs.get('src') if tag == 'script' else None
            if path and path.startswith('/static/') and urlsplit(path).path.endswith(('.css', '.js')):
                self.paths.append(path)

    parser = Assets()
    parser.feed(client.get('/').text)
    worker = client.get('/sw.js').text
    assert parser.paths
    for path in parser.paths:
        assert urlsplit(path).query, f'{path} needs a cache-busting revision'
        assert path in worker, f'{path} must be available in the offline app shell'
        assert client.get(path).headers['cache-control'] == 'no-cache'


def test_shell_icons_have_safe_intrinsic_sizes():
    from html.parser import HTMLParser

    class Icons(HTMLParser):
        def __init__(self):
            super().__init__()
            self.icons = []
        def handle_starttag(self, tag, attrs):
            if tag == 'svg':
                self.icons.append(dict(attrs))

    parser = Icons()
    parser.feed(client.get('/').text)
    assert parser.icons and all(icon.get('width') == '20' and icon.get('height') == '20' for icon in parser.icons)
