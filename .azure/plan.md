# Azure Deployment Plan - CricketCanClubsApp

## Status
Ready for Validation

## Goal
Deploy the Heartlake / CricketCanClubs club website to Azure with minimal code changes, while preserving the current FastAPI app, SQLite persistence, static UI, archive uploads, and club-scoped workflows.

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
- Deployment target recommendation: Azure VM first
- Reason:
  - Lowest friction for the current architecture
  - Keeps SQLite, local OCR helpers, and local model integration intact
  - Avoids immediate refactor to managed database or multi-service hosting

## Azure Context
- Subscription: `Subscription 1`
- Region: `Canada Central`

## Recommended Azure Architecture
- Azure Virtual Machine running Linux
- Nginx as reverse proxy
- Uvicorn / FastAPI behind systemd or a process manager
- Managed disk for app files and SQLite data
- Azure DNS for `criccanclubs.ca`
- Optional Azure Blob Storage later for uploads/backups if needed

## Why Not App Service First
- App Service is a cleaner managed web hosting option, but the current app depends on:
  - SQLite persistence
  - local file uploads and duplicate folders
  - local OCR / local model workflows
- That would require more refactoring before production use.

## App Components to Preserve
- Registration and sign-in pages
- Club selection and club-scoped dashboard
- Season setup for 2026, 2027, and beyond
- Player availability workflows
- Match center, scoring, archive import, and commentary
- Local assistant / RAG-style chat grounded in persisted data

## Azure Resources to Create
- Resource group
- Linux VM
- Network security group
- Public IP
- Managed disk
- DNS zone for custom domain
- Optional storage account for future backups/uploads

## Custom Domain Plan
- Domain target: `criccanclubs.ca`
- DNS approach:
  - Point registrar nameservers to Azure DNS, or
  - Add A/CNAME records to the VM public endpoint
- HTTPS:
  - Use Nginx + Let’s Encrypt initially on the VM

## Security Plan
- Restrict inbound access to:
  - 80 / 443
  - SSH from trusted IP only
- Use strong VM authentication
- Store secrets outside the repo
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
  - store them on persistent VM disk
  - exclude them from Git and deployment artifacts
  - restore them from backup or initial seed on first deploy
- To avoid data loss, also generate checked-in JSON snapshots from the current persisted state:
  - seed JSON for clubs, members, teams, fixtures, archives, and profiles
  - archive JSON exports for reviewed scorecards
  - duplicate-review metadata JSON
- These JSON snapshots act as the versioned recovery source in Git, while the live VM keeps the writable SQLite/runtime folders.

## Risks
- SQLite is not ideal for horizontal scale
- Local OCR / local model workflows are not cloud-managed yet
- VM requires patching and basic ops ownership

## Future Upgrade Path
- Move uploads to Blob Storage
- Move persistence to Azure SQL or PostgreSQL if needed
- Move OCR/chat workloads to Azure AI services if local compute becomes limiting
- Reevaluate App Service after the app is decoupled from local files and local inference

## Implementation Steps
1. Confirm Azure subscription and deployment region.
2. Validate the app for Azure readiness.
3. Generate infrastructure for the recommended VM-based deployment.
4. Add domain and HTTPS configuration.
5. Deploy and verify the website.

## Approval Needed
This plan is ready for review. After approval, proceed to validation and infrastructure generation.
