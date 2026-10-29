@echo off
REM Phone app (Expo Go) showing the website running on THIS laptop (python app\main.py), not Azure.
REM For testing changes before they are on Azure. mobile\README.md. Double-click or run .\start_phone_app_local.bat
cd /d "%~dp0mobile"
set IP=
for /f "usebackq delims=" %%i in (`powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -match 'Wi-Fi|Wireless|WLAN' -and $_.IPAddress -notlike '169.*' } | Select-Object -First 1).IPAddress"`) do set IP=%%i
if "%IP%"=="" (
  echo Couldn't find this laptop's Wi-Fi address. Is the laptop on Wi-Fi?
  pause
  exit /b 1
)
set EXPO_PUBLIC_BASE_URL=http://%IP%:8090
echo.
echo The app will show the website from this laptop: %EXPO_PUBLIC_BASE_URL%
echo 1. Keep the app running in another window:  python app\main.py
echo 2. Phone on the same Wi-Fi. If Windows asks to allow Python on the network, allow Private networks.
echo 3. Scan the QR code below with Expo Go.
echo.
if not exist node_modules call npm install
call npx expo start --clear
pause
