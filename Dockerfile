# Rental management — Flask + Gunicorn + SQLite
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    FLASK_DEBUG=0 \
    PORT=5050 \
    GUNICORN_WORKERS=1 \
    GUNICORN_TIMEOUT=60 \
    DB_PATH=/data/rental_system.db

RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

COPY . .

RUN mkdir -p /data \
    && chown -R app:app /app

EXPOSE 5050

# Uses PORT env (default 5050). Increase start-period on slow disks if needed.
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD curl -fsS http://127.0.0.1:5050/healthz >/dev/null || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
