#!/usr/bin/env bash
# Build and run the rental app with Docker Compose (V2 plugin or legacy docker-compose).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

# Prefer `docker compose` (Compose V2 plugin). Ubuntu docker.io alone often lacks it — see README hint below.
compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    docker compose "$@"
  elif docker-compose --version >/dev/null 2>&1; then
    docker-compose "$@"
  else
    echo "Docker Compose is not available." >&2
    echo "On Ubuntu 22.04 install the plugin, then log out and back in:" >&2
    echo "  sudo apt update && sudo apt install -y docker-compose-v2" >&2
    echo "Or use standalone: sudo apt install -y docker-compose" >&2
    exit 1
  fi
}

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
    compose_cmd build --pull
    ;;
  up)
    ensure_env_hint
    compose_cmd up -d --build
    compose_cmd ps
    echo ""
    echo "App: http://127.0.0.1:${DOCKER_HOST_PORT:-5050}/healthz"
    ;;
  down)
    compose_cmd down
    ;;
  restart)
    compose_cmd restart web
    ;;
  logs)
    compose_cmd logs -f web
    ;;
  ps)
    compose_cmd ps -a
    ;;
  shell)
    compose_cmd exec web bash -il || compose_cmd exec web sh -il
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
