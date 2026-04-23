# Azure App Service Deployment Notes

This template provisions:
- Linux App Service plan
- Linux Web App
- App settings for persistent SQLite/uploads/duplicates storage

## Inputs
- `location`: `Canada Central`
- `namePrefix`: resource prefix for the App Service resources
- `webAppName`: the final App Service name

## Data Safety
Runtime files are stored in App Service persistent storage under `/home/site/heartlake`:
- `heartlake.db`
- `store_cache.json`
- `dashboard_cache.json`
- `uploads/`
- `duplicates/`

## Notes
- GitHub Actions should deploy on push to `main`.
- The workflow will use the App Service publish profile secret.
- If OCR/LLM workloads stay local-only, the App Service stays lightweight for the web app itself.
