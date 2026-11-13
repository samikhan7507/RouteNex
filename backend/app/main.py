"""RouteNex API + built SPA entrypoint. Run migrations/bootstrap explicitly before start."""
from __future__ import annotations
import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from starlette.middleware.trustedhost import TrustedHostMiddleware

import sys
from app import __version__
from app.core.config import ROOT, get_settings
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from app.api import admin, auth, driver, fleet, ml, ops, payments, places, shop, trips, wallet
from app.db import engine, ready
from app.services import assistant

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("routenex")
DIST = ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not ready():
        raise RuntimeError("PostgreSQL is unavailable. Start it and run: alembic upgrade head")
    with engine.connect() as conn:
        try:
            version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception:
            raise RuntimeError("Database schema is not migrated. Run: alembic upgrade head")
        if version != "0002":
            raise RuntimeError(f"Database schema {version} is not current. Run: alembic upgrade head")
    log.info("RouteNex %s ready (env=%s, payments=%s)", __version__, settings.app_env, settings.payment_provider)
    yield
    engine.dispose()


app = FastAPI(title="RouteNex API", version=__version__, description="Local commerce, rides, parcels and fleet operations on PostgreSQL",
              lifespan=lifespan, docs_url=None if settings.is_production else "/docs", redoc_url=None if settings.is_production else "/redoc")
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.hosts)
app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                   allow_headers=["Content-Type", "X-CSRF-Token", "Authorization"])


@app.middleware("http")
async def context_and_limits(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > 1_100_000:
        return JSONResponse(status_code=413, content={"detail": "Request body too large"})
    start = time.monotonic()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(self), camera=(), microphone=()"
    response.headers["X-Frame-Options"] = "DENY"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' https://checkout.razorpay.com; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://*.tile.openstreetmap.org; "
            "connect-src 'self' https://*.razorpay.com; font-src 'self' data:; manifest-src 'self'; worker-src 'self'; "
            "frame-src https://*.razorpay.com; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")
    if settings.secure_cookies:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Server-Timing"] = f"app;dur={1000 * (time.monotonic() - start):.1f}"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    first = exc.errors()[0]
    location = ".".join(str(p) for p in first["loc"] if p not in ("body", "query"))
    return JSONResponse(status_code=422, content={"detail": f"{location}: {first['msg']}" if location else first["msg"]})


@app.exception_handler(IntegrityError)
async def integrity_error(request: Request, exc: IntegrityError):
    log.warning("Integrity conflict on %s (%s)", request.url.path, request.state.request_id)
    return JSONResponse(status_code=409, content={"detail": "This change conflicts with existing data. Refresh and try again"})


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    log.exception("Unhandled error on %s (%s)", request.url.path, getattr(request.state, "request_id", ""))
    return JSONResponse(status_code=500, content={"detail": "Something went wrong. Please try again or contact support with the request ID"})


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok", "service": "RouteNex", "version": __version__}


@app.get("/api/ready", tags=["system"])
def readiness():
    if not ready():
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unavailable"})
    return {"status": "ready", "database": "postgresql"}


for module in (auth, shop, trips, driver, fleet, ops, payments, wallet, places, admin, ml, assistant):
    app.include_router(module.router)


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        return JSONResponse(status_code=404, content={"detail": "API endpoint not found"})
    if not DIST.exists():
        return JSONResponse(status_code=503, content={"detail": "Frontend is not built. Run: cd frontend && npm ci && npm run build"})
    candidate = (DIST / path).resolve()
    if path and candidate.is_relative_to(DIST.resolve()) and candidate.is_file():
        cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
        return FileResponse(candidate, headers={"Cache-Control": cache})
    return FileResponse(DIST / "index.html", headers={"Cache-Control": "no-cache"})
