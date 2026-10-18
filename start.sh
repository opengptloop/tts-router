#!/usr/bin/env bash
# Developer helper: run TTS Studio from this source tree.
#
# The published way to run the app is simply:
#
#     pip install tts-studio
#     tts-studio
#
# This script is for hacking on the source: it installs the repo in editable
# mode, builds the frontend bundle if it is missing, then launches the app.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- pick a Python interpreter (override with PYTHON=/path/to/python) ------
if [[ -n "${PYTHON:-}" ]]; then
  PY="$PYTHON"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
else
  PY="$(command -v python3 || command -v python || true)"
fi
if [[ -z "$PY" ]]; then
  echo "error: no Python interpreter found" >&2
  exit 1
fi

# --- editable install (first run only) ---------------------------------------
if ! "$PY" -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
  echo ">> Installing tts-studio in editable mode..."
  "$PY" -m pip install -e "$ROOT"
fi

# --- rebuild the frontend bundle if it is missing ----------------------------
if [[ ! -f "$ROOT/src/tts_studio/frontend_dist/index.html" ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "error: frontend_dist missing and npm not found; install Node.js 20+ and run: (cd frontend && npm install && npm run build)" >&2
    exit 1
  fi
  echo ">> Building frontend..."
  (cd "$ROOT/frontend" && npm install --no-audit --no-fund && npm run build)
  rm -rf "$ROOT/src/tts_studio/frontend_dist"
  cp -r "$ROOT/frontend/dist" "$ROOT/src/tts_studio/frontend_dist"
fi

exec "$PY" -m tts_studio "$@"
