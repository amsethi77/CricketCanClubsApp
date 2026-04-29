#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESOURCE_GROUP="${RESOURCE_GROUP:-cricketcanclubs-rg}"
WEBAPP_NAME="${WEBAPP_NAME:-cricketcanclubs-web}"
ZIP_FILE="${ZIP_FILE:-/tmp/heartlake-cricket-app-azure.zip}"
DEPLOY_APPROVED="${DEPLOY_APPROVED:-no}"

cd "$ROOT_DIR"

if [[ "$DEPLOY_APPROVED" != "yes" ]]; then
  echo "Azure deployment is paused by default."
  echo "Run with DEPLOY_APPROVED=yes only after local testing and explicit approval."
  exit 1
fi

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
