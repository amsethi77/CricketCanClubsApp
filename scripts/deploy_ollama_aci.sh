#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE_FILE="$ROOT_DIR/infra/ollama-aci.yaml"
RENDERED_FILE="$(mktemp /tmp/ollama-aci.XXXXXX.yaml)"

RESOURCE_GROUP="${RESOURCE_GROUP:-cricketcanclubs-ollama-rg}"
LOCATION="${LOCATION:-canadacentral}"
ACI_NAME="${ACI_NAME:-cricketcanclubs-ollama}"
DNS_LABEL="${DNS_LABEL:-cricketcanclubs-ollama}"
STORAGE_ACCOUNT="${STORAGE_ACCOUNT:-ccollama$(date +%y%m%d%H%M%S)}"
SHARE_NAME="${SHARE_NAME:-ollama-models}"
OLLAMA_IMAGE="${OLLAMA_IMAGE:-ollama/ollama:latest}"
OLLAMA_MODEL="${OLLAMA_MODEL:-llama3.2:latest}"
OLLAMA_EMBED_MODEL="${OLLAMA_EMBED_MODEL:-nomic-embed-text}"
CPU="${CPU:-2}"
MEMORY_GB="${MEMORY_GB:-4}"
OWNER_TAG="${OWNER_TAG:-amitsethi}"
PROJECT_TAG="${PROJECT_TAG:-CricketClubApp}"
WEBAPP_RESOURCE_GROUP="${WEBAPP_RESOURCE_GROUP:-}"
WEBAPP_NAME="${WEBAPP_NAME:-}"

cleanup() {
  rm -f "$RENDERED_FILE"
}
trap cleanup EXIT

if ! command -v az >/dev/null 2>&1; then
  echo "Azure CLI (az) is required."
  exit 1
fi

python3 - <<PY
from pathlib import Path
template = Path("$TEMPLATE_FILE").read_text()
replacements = {
    "__LOCATION__": "${LOCATION}",
    "__ACI_NAME__": "${ACI_NAME}",
    "__DNS_LABEL__": "${DNS_LABEL}",
    "__STORAGE_ACCOUNT__": "${STORAGE_ACCOUNT}",
    "__STORAGE_KEY__": "__STORAGE_KEY__",
    "__SHARE_NAME__": "${SHARE_NAME}",
    "__OLLAMA_IMAGE__": "${OLLAMA_IMAGE}",
    "__OLLAMA_MODEL__": "${OLLAMA_MODEL}",
    "__CPU__": "${CPU}",
    "__MEMORY_GB__": "${MEMORY_GB}",
}
for key, value in replacements.items():
    template = template.replace(key, value)
Path("$RENDERED_FILE").write_text(template)
PY

az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --tags Owner="$OWNER_TAG" Project="$PROJECT_TAG" >/dev/null

if ! az storage account show --name "$STORAGE_ACCOUNT" --resource-group "$RESOURCE_GROUP" >/dev/null 2>&1; then
  az storage account create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$STORAGE_ACCOUNT" \
    --location "$LOCATION" \
    --sku Standard_LRS \
    --kind StorageV2 >/dev/null
fi

if [[ "$(az storage share exists --name "$SHARE_NAME" --account-name "$STORAGE_ACCOUNT" --query exists -o tsv)" != "true" ]]; then
  az storage share create \
    --name "$SHARE_NAME" \
    --account-name "$STORAGE_ACCOUNT" >/dev/null
fi

STORAGE_KEY="$(az storage account keys list \
  --resource-group "$RESOURCE_GROUP" \
  --account-name "$STORAGE_ACCOUNT" \
  --query "[0].value" \
  --output tsv)"

python3 - <<PY
from pathlib import Path
path = Path("$RENDERED_FILE")
content = path.read_text()
content = content.replace("__STORAGE_KEY__", "${STORAGE_KEY}")
path.write_text(content)
PY

az container delete \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACI_NAME" \
  --yes >/dev/null 2>&1 || true

az container create \
  --resource-group "$RESOURCE_GROUP" \
  --file "$RENDERED_FILE"

FQDN="$(az container show \
  --resource-group "$RESOURCE_GROUP" \
  --name "$ACI_NAME" \
  --query "ipAddress.fqdn" \
  --output tsv)"

echo "Waiting for Ollama to answer on http://${FQDN}:11434 ..."
for _ in $(seq 1 30); do
  if curl -fsS --max-time 5 "http://${FQDN}:11434/api/tags" >/dev/null 2>&1; then
    break
  fi
  sleep 10
done

curl -fsS \
  -X POST "http://${FQDN}:11434/api/pull" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"${OLLAMA_MODEL}\",\"stream\":false}" >/dev/null

if [[ -n "$OLLAMA_EMBED_MODEL" ]]; then
  curl -fsS \
    -X POST "http://${FQDN}:11434/api/pull" \
    -H "Content-Type: application/json" \
    -d "{\"model\":\"${OLLAMA_EMBED_MODEL}\",\"stream\":false}" >/dev/null
fi

if [[ -n "$WEBAPP_NAME" ]]; then
  WEBAPP_RESOURCE_GROUP="${WEBAPP_RESOURCE_GROUP:-$RESOURCE_GROUP}"
  az webapp config appsettings set \
    --resource-group "$WEBAPP_RESOURCE_GROUP" \
    --name "$WEBAPP_NAME" \
    --settings \
      OLLAMA_BASE_URL="http://${FQDN}:11434" \
      OLLAMA_MODEL="$OLLAMA_MODEL" \
      OLLAMA_EMBED_MODEL="$OLLAMA_EMBED_MODEL" >/dev/null
  echo "Updated web app settings for ${WEBAPP_NAME}."
fi

echo "Ollama ACI is deploying at: http://${FQDN}:11434"
echo "Use this in the web app as OLLAMA_BASE_URL=http://${FQDN}:11434"
