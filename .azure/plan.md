# Azure Deployment Plan - CricketCanClubsApp

## Status
Validated

## Goal
Deploy the Heartlake / CricketCanClubs club website to Azure App Service with GitHub Actions, while preserving the current FastAPI app, SQLite persistence, static UI, archive uploads, and club-scoped workflows.

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

## Recommended Azure Architecture
- Azure App Service on Linux
- GitHub Actions deployment from the repo main branch
- Persistent App Service storage for SQLite/uploads/duplicates under `/home/site/heartlake`
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

## Azure Resources to Create
- Resource group
- Linux App Service plan
- Linux Web App
- Azure DNS zone for custom domain
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
- Later move sensitive values to Key Vault if the app is expanded

## Data Plan
- Keep SQLite for the first Azure release
- Back up the database and upload folders regularly
- Preserve:
  - `app/data/heartlake.db`
  - `app/data/*.db`
  - `app/data/*_cache.json`
  - `app/uploads/`
  - `app/duplicates/`
  - user/profile data
- Treat these as runtime state, not source code:
  - store them in App Service persistent storage under `/home/site/heartlake`
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
- Move persistence to Azure SQL or PostgreSQL if needed
- Move OCR/chat workloads to Azure AI services if local compute becomes limiting
- Reevaluate App Service scaling after the app is decoupled from local files and local inference

## Implementation Steps
1. Confirm Azure subscription and deployment region.
2. Validate the app for Azure readiness.
3. Generate infrastructure for the recommended App Service deployment.
4. Add GitHub Actions deployment workflow.
5. Add domain and HTTPS configuration.
6. Deploy and verify the website.

## Approval Needed
This plan is ready for review. After approval, proceed to validation and infrastructure generation.

## Validation Proof
- `python3 -m compileall app` — passed; all Python modules under `app/` compiled successfully.
- `az bicep build --file infra/main.bicep` — passed; Bicep template compiled successfully.
- `git diff --check` — passed; no whitespace or patch-format issues in the working tree.
