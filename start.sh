#!/usr/bin/env bash
# Start TTS Studio: backend API + frontend dev server, shut down together.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
BACKEND_HOST="${TTS_HOST:-127.0.0.1}"
BACKEND_PORT="${TTS_PORT:-8000}"
FRONTEND_PORT="${TTS_FRONTEND_PORT:-5173}"

# --- pick a Python interpreter (override with PYTHON=/path/to/python) ------
if [[ -n "${PYTHON:-}" ]]; then
  PY="$PYTHON"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
elif [[ -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  PY="$BACKEND_DIR/.venv/bin/python"
else
  PY="$(command -v python3 || command -v python || true)"
fi
if [[ -z "$PY" ]]; then
  echo "error: no Python interpreter found" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "error: npm not found; install Node.js 20+" >&2
  exit 1
fi

# --- dependencies (first run only) ------------------------------------------
if ! "$PY" -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
  echo ">> Installing backend dependencies..."
  "$PY" -m pip install -e "$BACKEND_DIR"
fi
if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo ">> Installing frontend dependencies..."
  (cd "$FRONTEND_DIR" && npm install)
fi

# --- start both processes ----------------------------------------------------
BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  trap - INT TERM EXIT
  echo
  echo ">> Shutting down..."
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

echo ">> Starting backend on http://$BACKEND_HOST:$BACKEND_PORT"
(
  cd "$BACKEND_DIR"
  exec "$PY" run.py --host "$BACKEND_HOST" --port "$BACKEND_PORT"
) &
BACKEND_PID=$!

echo ">> Starting frontend on http://localhost:$FRONTEND_PORT"
(
  cd "$FRONTEND_DIR"
  export VITE_API_TARGET="http://$BACKEND_HOST:$BACKEND_PORT"
  exec npm run dev -- --port "$FRONTEND_PORT" --strictPort
) &
FRONTEND_PID=$!

echo
echo "   Backend:  http://$BACKEND_HOST:$BACKEND_PORT  (API docs at /docs)"
echo "   Frontend: http://localhost:$FRONTEND_PORT"
echo "   Press Ctrl+C to stop both."
echo

wait -n
