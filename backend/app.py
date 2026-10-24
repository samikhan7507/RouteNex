import config
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import time
from db import init_db, one
from routers import auth, shop, rides, fleet, ops, driver, wallet, ml, assistant
from services.errors import ApiError
from services.bootstrap import ensure_demo_data
from services import mlserve


# Scripts only from us + Leaflet CDN; no inline scripts/handlers. Map tiles + OSRM routing explicitly allowed.
CSP = ("default-src 'self'; script-src 'self' https://unpkg.com; style-src 'self' 'unsafe-inline' https://unpkg.com; "
       "img-src 'self' data: https://*.tile.openstreetmap.org https://unpkg.com; connect-src 'self' https://router.project-osrm.org; "
       "font-src 'self' data:; manifest-src 'self'; worker-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
# The service worker's own fetches (map tiles, Leaflet) are governed by the CSP served WITH sw.js.
SW_CSP = "default-src 'self'; connect-src 'self' https://unpkg.com https://*.tile.openstreetmap.org"
FRONTEND = config.ROOT / "frontend"


@asynccontextmanager
async def lifespan(_):
    init_db()
    ensure_demo_data()
    mlserve.ensure_models()           # first start only: trains the models in the background (about 10 s)
    if config.INSECURE_SECRET:
        print("WARNING: ROUTENEX_SECRET is not set - using an insecure dev secret.")
    yield


app = FastAPI(title="RouteNex API", version="2.3.0-phase5", description="Dynamic logistics, ride matching and fleet coordination API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    r = await call_next(request)
    r.headers.setdefault("X-Content-Type-Options", "nosniff")
    r.headers.setdefault("X-Frame-Options", "DENY")
    r.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    r.headers.setdefault("Permissions-Policy", "geolocation=(self)")
    path = request.url.path
    if path.startswith("/api"):
        r.headers.setdefault("Cache-Control", "no-store")
    if not path.startswith(("/docs", "/redoc", "/openapi")):   # Swagger UI needs its own CDN scripts
        r.headers.setdefault("Content-Security-Policy", CSP)
    return r


@app.exception_handler(RequestValidationError)
async def validation_error(_, exc: RequestValidationError):
    e = exc.errors()[0]
    loc = ".".join(str(p) for p in e["loc"] if p != "body")
    return JSONResponse(status_code=422, content={"detail": f"{loc}: {e['msg']}" if loc else e["msg"]})  # string, so the UI toast is readable


@app.exception_handler(ApiError)
async def api_error(_, exc: ApiError):
    return JSONResponse(status_code=exc.status, content={"detail": exc.detail})


@app.get("/api/health")
def health():
    try:
        one("SELECT 1 n")
        db = "ok"
    except Exception:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "db": "down"})
    return {"status": "healthy", "service": "RouteNex", "db": db, "time": int(time.time())}


for m in (auth, shop, rides, fleet, ops, driver, wallet, ml, assistant):
    app.include_router(m.router)


@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache"})


# PWA files must live at the site root so the service worker can control the whole app ("/" scope).
@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(FRONTEND / "sw.js", media_type="application/javascript", headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/", "Content-Security-Policy": SW_CSP})


@app.get("/manifest.webmanifest", include_in_schema=False)
def manifest():
    return FileResponse(FRONTEND / "manifest.webmanifest", media_type="application/manifest+json", headers={"Cache-Control": "no-cache"})


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return FileResponse(FRONTEND / "icons" / "icon-192.png", media_type="image/png")


app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
