@echo off
REM Push this project to GitHub (README "Pushing to GitHub"). Double-click to run.
REM Never pushes .env (secrets), DB-Backup or scorecard_reports.
cd /d "%~dp0"
echo === Getting the latest from GitHub ===
git pull --no-rebase
if errorlevel 1 (
  echo.
  echo git pull had a problem ^(see above^). Nothing was pushed. Send Claude a screenshot.
  pause
  exit /b 1
)
echo === Adding changes ===
git add -A -- . ":(exclude)DB-Backup" ":(exclude)scorecard_reports"
git diff --cached --name-only | findstr /r /i "^\.env$ \.env$" >nul
if not errorlevel 1 (
  git reset -q -- .env
  echo .env was taken out of the push - it holds secret keys and must never go to GitHub.
)
git diff --cached --quiet
if not errorlevel 1 (
  echo Nothing new to push.
  pause
  exit /b 0
)
set MSG=%*
if "%MSG%"=="" set MSG=Updates from Dhruvika and Claude
git commit -m "%MSG%" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
echo === Pushing ===
git push
if errorlevel 1 (
  echo.
  echo Push failed ^(see above^). Send Claude a screenshot.
) else (
  echo.
  echo Done: pushed to GitHub.
)
pause
