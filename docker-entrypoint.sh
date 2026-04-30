#!/bin/sh
set -e

run_server() {
  PORT="${PORT:-5050}"
  WORKERS="${GUNICORN_WORKERS:-1}"
  TIMEOUT="${GUNICORN_TIMEOUT:-60}"

  exec gunicorn \
    --bind "0.0.0.0:${PORT}" \
    --workers "${WORKERS}" \
    --timeout "${TIMEOUT}" \
    --access-logfile "-" \
    --error-logfile "-" \
    --capture-output \
    app:app
}

if [ "$(id -u)" = "0" ]; then
  mkdir -p /data
  chown -R app:app /data
  exec gosu app /docker-entrypoint.sh
fi

run_server
