# Ollama on Azure Container Instances

This repo uses Azure App Service for the web app and Azure Container Instances for the Ollama runtime.

## Why ACI

- Ollama binds to `11434` and can be exposed as a separate HTTP service.
- Azure Container Instances are a lightweight fit for a single Ollama endpoint.
- Azure Files gives the container persistent model storage so restarts do not wipe downloads.

## Official references

- Ollama Docker: https://docs.ollama.com/docker
- Ollama API: https://docs.ollama.com/api
- Azure Container Instances container groups: https://learn.microsoft.com/en-us/azure/container-instances/container-instances-container-groups
- Azure Files mount for ACI: https://learn.microsoft.com/en-us/azure/container-instances/container-instances-volume-azure-files

## Deploy

Run:

```bash
scripts/deploy_ollama_aci.sh
```

The script:

1. Creates or reuses the resource group.
2. Creates or reuses the storage account and Azure Files share.
3. Renders [`infra/ollama-aci.yaml`](../infra/ollama-aci.yaml) with the live storage key.
4. Deploys the container group with `ollama/ollama`.

## Runtime settings

Recommended environment values for the web app:

```bash
OLLAMA_BASE_URL=http://<aci-fqdn>:11434
OLLAMA_MODEL=llama3.2:latest
```

The app already reads `OLLAMA_BASE_URL` in [`app/cricket_brain.py`](../app/cricket_brain.py).

## Health check

After deployment:

1. Open `http://<aci-fqdn>:11434/api/tags` to confirm Ollama is live.
2. Open `/api/health` on the Azure web app and confirm the `llm.provider` changes from `heuristic` to `ollama`.
