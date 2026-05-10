#!/usr/bin/env bash
# Launch the LoL Damage Predictor web server and open the page.
set -euo pipefail

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"
URL="http://${HOST}:${PORT}/"

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo "Python 3 not found on PATH"; exit 1; }

"$PY" -c "import requests" >/dev/null 2>&1 || {
    echo "[start.sh] installing dependency: requests"
    "$PY" -m pip install --quiet requests
}

# Pick a launcher per OS.
open_browser() {
    sleep 0.6
    if command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true
    elif command -v open >/dev/null 2>&1; then open "$URL" || true
    fi
}
open_browser &

exec "$PY" -m lol_damage.server --host "$HOST" --port "$PORT"
