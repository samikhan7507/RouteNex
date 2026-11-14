FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY frontend frontend
COPY database database
COPY ml ml
ENV ROUTENEX_DB=/app/database/routenex.db
WORKDIR /app/backend
EXPOSE 8000
# Seeds demo data the first time (no DB yet), then starts the API.
# 1 worker on purpose: SQLite + in-memory rate limiter. Move to Postgres + Redis before scaling workers.
CMD ["sh","-c","[ -f \"$ROUTENEX_DB\" ] || python /app/database/seed.py --reset; exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
