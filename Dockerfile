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
# Startup initializes tables and demo accounts without deleting existing data.
# Keep one worker while rate limits remain in memory.
CMD ["sh","-c","exec uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
