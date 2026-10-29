# Azure Deployment Plan - CricketCanClubsApp

## Status
Application redeployed and Gemini configured through Key Vault; Azure SQL data migration pending.

## Goal
Deploy the CricketClubApp / CricketCanClubs club website to Azure App Service with GitHub Actions, while preserving the current FastAPI app, SQLite persistence, static UI, archive uploads, and club-scoped workflows.

## Workspace Analysis
- Project type: Python FastAPI web application with static frontend assets.
- Current runtime dependencies:
  - FastAPI / Uvicorn
  - SQLite for persistence
  - Local upload and duplicate-review folders
  - Local OCR / local LLM integration
- Packaging pattern:
  - Single web app process
  - Static files served from the same app
  - No separate frontend build pipeline

## Deployment Mode
- Mode: Modernize / host existing app
- Deployment target recommendation: Azure App Service with GitHub Actions
- Reason:
  - Best fit for the requested GitHub-to-Azure deployment flow
  - Keeps the app lightweight and easy to redeploy from the repo
  - Works with the current FastAPI app once runtime data is kept outside the web root

## Azure Context
- Subscription: `Subscription 1`
- Region: `Canada Central`
- Tenant ID: `44402a74-5c2e-4982-a6fb-e70bb39c7d8a`

## Recommended Azure Architecture
- Azure App Service on Linux
- GitHub Actions deployment from the repo main branch
- Production: Azure SQL Database PaaS, logical server `cricketcanclubs-prod-sql`, database `cricketcanclubs-prod`, in Canada Central. The database is configured for the subscription's free limit, with auto-pause on exhaustion.
- Test: SQLite. Do not provision a second Azure SQL database for test because the free monthly allowance applies to only one database in the subscription.
- Keep the existing App Service SQLite database as the production source of truth until the SQL-compatible application backend and a backed-up, verified migration are complete.
- Canada Central Key Vault: `cricketcanclubs-prod-kv`. The Gemini secret and SQL administrator password are stored there. The App Service system-assigned managed identity has the Key Vault Secrets User role, and `GEMINI_API_KEY` references the Gemini secret. The former East US vault `testkeyvault179` was soft-deleted on 2026-10-28 and is recoverable during Azure's 90-day retention period; it was not permanently purged.
- Separate Azure Container Instance for Ollama with Azure Files persistence for downloaded models
- The Ollama container should pull both the chat model and an embedding model (`nomic-embed-text` by default) so the web app can use embeddings-backed grounding and chunk ranking.
- Azure DNS for `criccanclubs.ca`
- Optional Azure Blob Storage later for larger archive backups or media offload

## Delivery Path
- Source of truth: GitHub repository
- CI/CD mechanism: GitHub Actions
- Azure App Service deployment will be triggered from GitHub Actions on push to `main`.
- The workflow will package the app and deploy it directly to the App Service instance.

## App Components to Preserve
- Registration and sign-in pages
- Club selection and club-scoped dashboard
- Season setup for 2026, 2027, and beyond
- Player availability workflows
- Match center, scoring, archive import, and commentary
- Local assistant / RAG-style chat grounded in persisted data

## Existing and Provisioned Azure Resources
- Resource group: `cricketcanclubs-rg` (Canada Central)
- Linux App Service plan and Web App: `cricketcanclubs-plan`, `cricketcanclubs-web` (Canada Central)
- Production Azure SQL server and database: `cricketcanclubs-prod-sql`, `cricketcanclubs-prod` (Canada Central)
- Production Key Vault replacement: `cricketcanclubs-prod-kv` (Canada Central)
- Azure DNS zone for custom domain (existing status to verify)
- Optional storage account for future backups/uploads

## Custom Domain Plan
- Domain target: `criccanclubs.ca`
- DNS approach:
  - Point registrar nameservers to Azure DNS, or
  - Add A/CNAME records to the App Service endpoint
- HTTPS:
  - Use App Service managed HTTPS once the custom domain is validated

## Security Plan
- Restrict inbound access to HTTPS through App Service
- Store GitHub Actions publish profile as a repository secret
- Keep runtime data outside the code repository
- Use the Canada Central Key Vault for application secrets. The App Service managed identity and Gemini Key Vault reference are configured; do not put secret values in source or deployment packages.
- The SQL server currently has no firewall allow rules. Configure least-privilege SQL connectivity and access before connecting production.

## Data Plan
- Production SQL database is provisioned but empty and not connected to the app yet.
- Keep SQLite as the production source of truth until code, backup, migration, and SQL read/write validation are complete.
- Keep test on SQLite; no Azure SQL test database is planned.
- Back up the database and upload folders regularly
- Preserve:
  - `app/data/cricketclubapp.db`
  - `app/data/*.db`
  - `app/data/*_cache.json`
  - `app/uploads/`
  - `app/duplicates/`
  - user/profile data
- Treat these as runtime state, not source code:
  - store them in App Service persistent storage under `/home/site/cricketclubapp`
  - exclude them from Git and deployment artifacts
  - restore them from backup or initial seed on first deploy
- To avoid data loss, also generate checked-in JSON snapshots from the current persisted state:
  - seed JSON for clubs, members, teams, fixtures, archives, and profiles
  - archive JSON exports for reviewed scorecards
  - duplicate-review metadata JSON
- These JSON snapshots act as the versioned recovery source in Git, while the live App Service keeps the writable SQLite/runtime folders.

## Risks
- SQLite is not ideal for horizontal scale
- App Service scale-out is still limited by SQLite persistence
- Local OCR / local model workflows are not cloud-managed yet
- Managed storage still needs regular backup hygiene

## Future Upgrade Path
- Move uploads to Blob Storage
- Complete the SQLite-to-Azure SQL migration after the application has a SQL Server-compatible persistence layer
- Keep Ollama on Azure Container Instances for a lightweight model backend, or move OCR/chat workloads to Azure AI services if the local model path becomes limiting
- Reevaluate App Service scaling after the app is decoupled from local files and local inference

## Implementation Steps
1. Provisioned production Azure SQL server/database and replacement Key Vault in Canada Central.
2. Implement and test a SQL Server-compatible application persistence layer while retaining SQLite for test.
3. Back up the live App Service SQLite database, migrate it to Azure SQL, and verify record counts and application read/write behavior before cutover.
4. Configure SQL-specific least-privilege identity and narrowly scoped network access for the App Service. Key Vault access for Gemini is already configured and verified.
5. Before the 90-day retention period expires, confirm that no consumers require secrets from the soft-deleted East US Key Vault; recover it if required, otherwise allow Azure's scheduled purge.

## Direct CLI Login

Use the tenant below for direct Azure CLI access when deploying with [`scripts/deploy_azure.sh`](../scripts/deploy_azure.sh):

```bash
az logout
az cloud set --name AzureCloud
az login --use-device-code --tenant 44402a74-5c2e-4982-a6fb-e70bb39c7d8a
az account set --subscription 9fdb812c-a846-4890-a27d-b99edc274a5e
```

## Approval Needed
This plan is ready for review. After approval, proceed to validation and infrastructure generation.

## Validation Proof
- `python3 -m compileall app` — passed; all Python modules under `app/` compiled successfully.
- `az bicep build --file infra/main.bicep` — passed; Bicep template compiled successfully.
- 2026-10-28 production redeploy — Oryx build reported zero errors and deployment successful; `/api/health` returned `ok`; `/api/scorecards/reader` reported Gemini; synthetic extraction with the Key Vault secret returned the expected 17-run innings.
- Production remains on the existing SQLite database under `/home/site/cricketcanclubs`; Azure SQL is paused and empty pending a compatible backend and backed-up data migration.
- `git diff --check` — passed; no whitespace or patch-format issues in the working tree.
