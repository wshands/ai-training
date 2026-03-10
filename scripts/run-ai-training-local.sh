#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LANDING_PID_FILE="/tmp/aitrainops-landing-lite.pid"
LANDING_LOG_FILE="/tmp/aitrainops-landing-lite.log"

ACTION="up"
if [[ $# -gt 0 && "${1}" != --* ]]; then
  ACTION="$1"
  shift
fi

BUS="${BUS:-sqs}"                 # sqs | kafka
BUILD=1
START_LANDING=1
DOWN_VOLUMES=0
DOWN_ON_EXIT=0
UI_PORT="${UI_PORT:-3000}"
LANDING_PORT="${LANDING_PORT:-8080}"
EXTRA_ARGS=()

usage() {
  cat <<'EOF'
Usage:
  scripts/run-ai-training-local.sh [up|down|status|logs] [options]

Actions:
  up       Start local docker services, optional landing-lite, and UI dev server (default)
  down     Stop local docker services (and landing-lite server if started by script)
  status   Show docker compose service status
  logs     Tail docker compose logs (optionally pass service names)

Options:
  --bus <sqs|kafka>   Event bus stack to use (default: sqs)
  --no-build          Skip docker image build when running action "up"
  --no-landing        Do not start landing-lite local static server
  --ui-port <port>    UI dev server port (default: 3000)
  --landing-port <p>  landing-lite server port (default: 8080)
  --down-on-exit      Also run docker compose down when UI exits (action "up")
  --volumes           With action "down", remove docker volumes
  -h, --help          Show this help

Examples:
  scripts/run-ai-training-local.sh up --bus sqs
  scripts/run-ai-training-local.sh up --bus kafka --no-landing
  scripts/run-ai-training-local.sh down --bus sqs --volumes
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --bus)
      BUS="${2:-}"
      shift 2
      ;;
    --no-build)
      BUILD=0
      shift
      ;;
    --no-landing)
      START_LANDING=0
      shift
      ;;
    --ui-port)
      UI_PORT="${2:-}"
      shift 2
      ;;
    --landing-port)
      LANDING_PORT="${2:-}"
      shift 2
      ;;
    --down-on-exit)
      DOWN_ON_EXIT=1
      shift
      ;;
    --volumes)
      DOWN_VOLUMES=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      EXTRA_ARGS+=("$1")
      shift
      ;;
  esac
done

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 is required. Install it first." >&2
    exit 1
  fi
}

compose_file() {
  case "$BUS" in
    sqs) echo "$ROOT_DIR/docker-compose-elasticmq.yml" ;;
    kafka) echo "$ROOT_DIR/docker-compose-kafka.yml" ;;
    *)
      echo "Unsupported --bus value: $BUS (expected sqs or kafka)" >&2
      exit 1
      ;;
  esac
}

compose() {
  local file
  file="$(compose_file)"
  if [[ ! -f "$file" ]]; then
    echo "Compose file not found: $file" >&2
    exit 1
  fi
  docker compose -f "$file" "$@"
}

is_port_listening() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return $?
  fi
  return 1
}

start_landing() {
  if [[ "$START_LANDING" -eq 0 ]]; then
    return 0
  fi

  if ! command -v python3 >/dev/null 2>&1; then
    echo "python3 not found; skipping landing-lite local server." >&2
    return 0
  fi

  if [[ -f "$LANDING_PID_FILE" ]]; then
    local existing_pid
    existing_pid="$(cat "$LANDING_PID_FILE" 2>/dev/null || true)"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" >/dev/null 2>&1; then
      echo "landing-lite server already running on pid $existing_pid"
      return 0
    fi
    rm -f "$LANDING_PID_FILE"
  fi

  if is_port_listening "$LANDING_PORT"; then
    echo "Port $LANDING_PORT already in use; skipping landing-lite server startup."
    return 0
  fi

  python3 -m http.server "$LANDING_PORT" --directory "$ROOT_DIR/landing-lite" >"$LANDING_LOG_FILE" 2>&1 &
  echo $! >"$LANDING_PID_FILE"
  echo "landing-lite running at http://localhost:${LANDING_PORT} (pid $(cat "$LANDING_PID_FILE"))"
}

stop_landing() {
  if [[ ! -f "$LANDING_PID_FILE" ]]; then
    return 0
  fi
  local pid
  pid="$(cat "$LANDING_PID_FILE" 2>/dev/null || true)"
  if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid" >/dev/null 2>&1 || true
  fi
  rm -f "$LANDING_PID_FILE"
}

require_cmd docker
if ! docker info >/dev/null 2>&1; then
  echo "Docker daemon is not running. Start Docker Desktop and retry." >&2
  exit 1
fi

case "$ACTION" in
  up)
    require_cmd npm

    if [[ ! -f "$ROOT_DIR/.env.local" && -f "$ROOT_DIR/.env.local.example" ]]; then
      cp "$ROOT_DIR/.env.local.example" "$ROOT_DIR/.env.local"
      echo "Created .env.local from .env.local.example"
    fi

    compose_up_args=(up -d)
    if [[ "$BUILD" -eq 1 ]]; then
      compose_up_args+=(--build)
    fi
    compose_up_args+=(--force-recreate)

    echo "Starting local services with bus=${BUS}..."
    compose "${compose_up_args[@]}"

    start_landing

    ui_dir="$ROOT_DIR/control-plane/ui"
    if [[ ! -d "$ui_dir/node_modules" ]]; then
      echo "Installing UI dependencies (npm ci)..."
      (cd "$ui_dir" && npm ci)
    fi

    marketing_url="${REACT_APP_MARKETING_SITE_URL:-https://www.aitrainops.com}"
    if [[ "$START_LANDING" -eq 1 ]]; then
      marketing_url="http://localhost:${LANDING_PORT}"
    fi

    cleanup() {
      stop_landing
      if [[ "$DOWN_ON_EXIT" -eq 1 ]]; then
        echo "Stopping docker services (--down-on-exit enabled)..."
        compose down
      fi
    }
    trap cleanup EXIT INT TERM

    echo ""
    echo "Local services are up."
    echo "API docs:   http://localhost:8000/docs"
    echo "UI:         http://localhost:${UI_PORT}"
    if [[ "$START_LANDING" -eq 1 ]]; then
      echo "Landing:    http://localhost:${LANDING_PORT}"
    fi
    echo ""
    echo "Starting UI dev server (Ctrl+C to stop UI)..."

    cd "$ui_dir"
    REACT_APP_API_BASE_URL="http://localhost:8000" \
    REACT_APP_WS_BASE_URL="ws://localhost:8000" \
    REACT_APP_MARKETING_SITE_URL="$marketing_url" \
    PORT="$UI_PORT" \
    npm start
    ;;

  down)
    compose_down_args=(down)
    if [[ "$DOWN_VOLUMES" -eq 1 ]]; then
      compose_down_args+=(-v)
    fi
    compose "${compose_down_args[@]}"
    stop_landing
    echo "Local services stopped."
    ;;

  status)
    compose ps
    if [[ -f "$LANDING_PID_FILE" ]]; then
      pid="$(cat "$LANDING_PID_FILE" 2>/dev/null || true)"
      if [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1; then
        echo "landing-lite: running (pid $pid) on http://localhost:${LANDING_PORT}"
      else
        echo "landing-lite: pid file present but process is not running"
      fi
    else
      echo "landing-lite: not running"
    fi
    ;;

  logs)
    if [[ ${#EXTRA_ARGS[@]} -gt 0 ]]; then
      compose logs -f "${EXTRA_ARGS[@]}"
    else
      compose logs -f
    fi
    ;;

  *)
    echo "Unknown action: $ACTION" >&2
    usage
    exit 1
    ;;
esac
