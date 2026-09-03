# Azure Deployment Plan

Status: Ready for Validation

## Objective
Deploy the current redesigned Cricket Club application to the existing Azure App Service at `https://cricketcanclubs-web.azurewebsites.net`.

## Scope
- Keep the existing Azure site and resource group.
- Deploy the latest codebase in-place to the existing web app.
- Preserve the current database and uploaded data paths.
- Do not create a second parallel site in this deployment.

## Existing Azure Target
- Resource group: `cricketcanclubs-rg`
- App Service: `cricketcanclubs-web`
- Public URL: `https://cricketcanclubs-web.azurewebsites.net`

## Application Notes
- The app uses SQLite-backed data stored with the app content / data root.
- The deployment package excludes runtime data folders such as uploads, duplicates, and cache files.
- The public-facing pages now use the shared header system and the LIVE-first navigation model.
- Authenticated users keep the RBAC fixtures editor and the authenticated navigation set.

## Validation Steps
1. Run Python compile checks for the backend.
2. Run JavaScript syntax checks for the key static bundles.
3. Run local smoke / QA checks.
4. Verify the authenticated and public mobile layouts do not overflow.
5. Verify the authenticated Fixtures page still shows the RBAC editor.
6. Verify the public `/live`, `/fixtures`, `/rankings`, `/signin`, and `/register` pages render.

## Validation Proof
- Pending validation.

## Rollout Steps
1. Package the app with `scripts/deploy_azure.sh`.
2. Deploy to `cricketcanclubs-web`.
3. Verify the live site responds successfully.
4. Smoke-test the main routes after deployment.

## Approval
This plan is approved for validation and deployment of the existing Azure site only.
