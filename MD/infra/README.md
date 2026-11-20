# Azure App Service Deployment Notes

This template provisions:
- Linux App Service plan
- Linux Web App
- App settings for persistent SQLite/uploads/duplicates storage

The repo also includes [`infra/ollama-aci.yaml`](ollama-aci.yaml) and [`scripts/deploy_ollama_aci.sh`](../scripts/deploy_ollama_aci.sh) for the separate Ollama backend on Azure Container Instances.

## Inputs
- `location`: `Canada Central`
- `namePrefix`: resource prefix for the App Service resources
- `webAppName`: the final App Service name

## Data Safety
Runtime files are stored in App Service persistent storage under `/home/site/cricketclubapp`:
- `cricketclubapp.db`
- `store_cache.json`
- `dashboard_cache.json`
- `uploads/`
- `duplicates/`

## Notes
- GitHub Actions deploys ONLY by hand (Nov 20 2026): Actions -> "Deploy CricketCanClubs to Azure" -> Run workflow. A push to `main` does not deploy.
- Azure starts the app as `python -m uvicorn app.main:app` from `/home/site/wwwroot`; the pipeline's check starts it the same way.
- Free plan (F1): little CPU per 5 minutes / per day and 1 GB storage; when a CPU quota is used up Azure stops the app ("quota exceeded") until it resets (daily at midnight UTC). Deploying and starting the app use the most CPU. Basic (B1) has no CPU quota.
- Storage on /home: photos are stored under 450 KB, no duplicate copies, backups ~4 MB each (3 days kept).
- The workflow will use the App Service publish profile secret.
- If OCR/LLM workloads stay local-only, the App Service stays lightweight for the web app itself.
