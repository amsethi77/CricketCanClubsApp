#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESOURCE_GROUP="${RESOURCE_GROUP:-cricketcanclubs-rg}"
WEBAPP_NAME="${WEBAPP_NAME:-cricketcanclubs-web}"
ZIP_FILE="${ZIP_FILE:-/tmp/heartlake-cricket-app-azure.zip}"
DEPLOY_APPROVED="${DEPLOY_APPROVED:-no}"
BUILD_DIR="${BUILD_DIR:-/tmp/heartlake-cricket-app-build}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$ROOT_DIR"

if [[ "$DEPLOY_APPROVED" != "yes" ]]; then
  echo "Azure deployment is paused by default."
  echo "Run with DEPLOY_APPROVED=yes only after local testing and explicit approval."
  exit 1
fi

"$PYTHON_BIN" -m compileall app

rm -f "$ZIP_FILE"
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

if command -v rsync >/dev/null 2>&1; then
  rsync -a \
    --exclude 'app/data/**' \
    --exclude 'app/uploads/**' \
    --exclude 'app/duplicates/**' \
    --exclude 'app/__pycache__/**' \
    --exclude 'app/static/__pycache__/**' \
    --exclude 'app/**/__pycache__/**' \
    --exclude '.python_packages/**' \
    --exclude '.DS_Store' \
    app requirements.txt startup.sh "$BUILD_DIR"/
else
  cp -a app "$BUILD_DIR"/
  rm -rf "$BUILD_DIR/app/data" "$BUILD_DIR/app/uploads" "$BUILD_DIR/app/duplicates"
  find "$BUILD_DIR/app" -type d -name __pycache__ -prune -exec rm -rf {} +
  find "$BUILD_DIR/app" -name .DS_Store -type f -delete
  cp requirements.txt startup.sh "$BUILD_DIR"/
fi

cp MD/README.md "$BUILD_DIR/README.md"
cp MD/READMELLM.md "$BUILD_DIR/READMELLM.md"

"$PYTHON_BIN" -m pip install \
  --no-cache-dir \
  --only-binary=:all: \
  --platform manylinux2014_x86_64 \
  --implementation cp \
  --python-version 3.11 \
  --abi cp311 \
  -r "$BUILD_DIR/requirements.txt" \
  -t "$BUILD_DIR/.python_packages/lib/site-packages"

if command -v zip >/dev/null 2>&1; then
  (cd "$BUILD_DIR" && zip -r "$ZIP_FILE" app requirements.txt README.md READMELLM.md startup.sh .python_packages)
else
  (cd "$BUILD_DIR" && "$PYTHON_BIN" -m zipfile -c "$ZIP_FILE" app requirements.txt README.md READMELLM.md startup.sh .python_packages)
fi

az webapp deployment source config-zip \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --src "$ZIP_FILE"

az webapp restart \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME"

HOSTNAME="$(az webapp show --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" --query defaultHostName -o tsv)"
echo "Deployed to https://${HOSTNAME}"
