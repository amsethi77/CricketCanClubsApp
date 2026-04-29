#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESOURCE_GROUP="${RESOURCE_GROUP:-cricketcanclubs-rg}"
WEBAPP_NAME="${WEBAPP_NAME:-cricketcanclubs-web}"
ZIP_FILE="${ZIP_FILE:-/tmp/heartlake-cricket-app-azure.zip}"

cd "$ROOT_DIR"

python3 -m compileall app

rm -f "$ZIP_FILE"
zip -r "$ZIP_FILE" app requirements.txt README.md \
  -x 'app/data/**' \
     'app/uploads/**' \
     'app/duplicates/**' \
     'app/__pycache__/**' \
     'app/static/__pycache__/**' \
     'app/**/__pycache__/**' \
     '*.DS_Store'

az webapp deployment source config-zip \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME" \
  --src "$ZIP_FILE"

az webapp restart \
  --resource-group "$RESOURCE_GROUP" \
  --name "$WEBAPP_NAME"

HOSTNAME="$(az webapp show --resource-group "$RESOURCE_GROUP" --name "$WEBAPP_NAME" --query defaultHostName -o tsv)"
echo "Deployed to https://${HOSTNAME}"

