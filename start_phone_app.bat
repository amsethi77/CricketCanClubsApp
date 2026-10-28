@echo off
REM Start the CricketCanClubs phone app for Expo Go (mobile\README.md). Double-click to run.
cd /d "%~dp0mobile"
where node >nul 2>nul
if errorlevel 1 (
  echo Node.js is not installed. Install the LTS version from https://nodejs.org ^(Next on every screen^),
  echo then double-click this file again.
  pause
  exit /b 1
)
if not exist node_modules (
  echo === Installing the app's parts ^(first time only, a few minutes^) ===
  call npm install
)
echo.
echo === Starting. Open Expo Go on your phone and scan the QR code below. ===
echo === Phone and laptop must be on the same Wi-Fi. Close this window to stop. ===
echo.
call npx expo start
pause
