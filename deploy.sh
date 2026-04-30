#!/usr/bin/env bash
# Build and run the rental app with Docker Compose (Docker Compose V2 plugin).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

usage() {
  echo "Usage: $0 [command]"
  echo ""
  echo "Commands:"
  echo "  build     Build image (--pull)"
  echo "  up        Build if needed and start detached"
  echo "  down      Stop and remove containers"
  echo "  restart   Restart web service"
  echo "  logs      Follow web logs"
  echo "  ps        Show compose status"
  echo "  shell     Open shell inside running web container (debug)"
}

ensure_env_hint() {
  if [[ ! -f .env ]]; then
    echo "Note: no .env file — copy .env.example to .env and set SECRET_KEY for production."
  fi
}

case "${1:-up}" in
  build)
    docker compose build --pull
    ;;
  up)
    ensure_env_hint
    docker compose up -d --build
    docker compose ps
    echo ""
    echo "App: http://127.0.0.1:${DOCKER_HOST_PORT:-5050}/healthz"
    ;;
  down)
    docker compose down
    ;;
  restart)
    docker compose restart web
    ;;
  logs)
    docker compose logs -f web
    ;;
  ps)
    docker compose ps -a
    ;;
  shell)
    docker compose exec web bash -il || docker compose exec web sh -il
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    echo "Unknown command: $1"
    usage
    exit 1
    ;;
esac
