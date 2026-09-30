#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
PORT="${PORT:-8091}"
HOST="${HOST:-0.0.0.0}"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.venv}"

create_venv() {
  "$PYTHON_BIN" -m venv --system-site-packages "$VENV_DIR"
}

if [ ! -d "$VENV_DIR" ]; then
  create_venv
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

if ! python - <<'PY' >/dev/null 2>&1
import fastapi, uvicorn, httpx, multipart
PY
then
  if [ ! -f "$VENV_DIR/pyvenv.cfg" ] || ! rg -q "include-system-site-packages = true" "$VENV_DIR/pyvenv.cfg"; then
    deactivate || true
    rm -rf "$VENV_DIR"
    create_venv
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
  fi
fi

if ! python - <<'PY' >/dev/null 2>&1
import fastapi, uvicorn, httpx, multipart
PY
then
  python -m pip install --disable-pip-version-check -r requirements.txt
fi

export PORT HOST
export PYTHONPATH="$ROOT_DIR/app:${PYTHONPATH:-}"

echo "Starting CricketCanClubsApp on http://127.0.0.1:${PORT}"
exec python app/main.py
