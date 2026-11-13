# RouteNex v3 — multi-stage production image (React SPA + FastAPI + PostgreSQL client).
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    DEMO_MODE=false \
    DEMO_AUTOPILOT=false \
    SEED_DEMO_DATA=false \
    PAYMENT_PROVIDER=razorpay \
    OTP_PROVIDER=twilio \
    LOCATION_PROVIDER=local
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/app backend/app
COPY alembic.ini ./
COPY migrations migrations
COPY scripts scripts
COPY ml ml
COPY --from=web /web/dist frontend/dist
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=5s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"
# Migrations are explicit; bootstrap only ensures the configured admin (never seeds demo data in production).
CMD ["sh", "-c", "alembic upgrade head && python scripts/bootstrap.py && exec uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
