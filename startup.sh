#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SITE_PACKAGES="$ROOT_DIR/.python_packages/lib/site-packages"

mkdir -p "$SITE_PACKAGES"

if [[ ! -d "$SITE_PACKAGES/uvicorn" ]]; then
  python -m pip install --no-cache-dir --target "$SITE_PACKAGES" -r "$ROOT_DIR/requirements.txt"
fi

export PYTHONPATH="$SITE_PACKAGES${PYTHONPATH:+:$PYTHONPATH}"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
