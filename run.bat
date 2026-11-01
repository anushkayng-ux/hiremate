@echo off
setlocal
title HireMate
cd /d "%~dp0"
set "LOG=%~dp0setup_log.txt"
echo HireMate setup log %DATE% %TIME% > "%LOG%"
echo.
echo  ===============================
echo   HireMate - starting up
echo  ===============================
echo.

rem ---- find a real Python 3.10+ (skips the Microsoft Store shortcut)
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul && set "PY=python"
if not defined PY goto nopython
%PY% --version >> "%LOG%" 2>&1
echo  Python found:
%PY% --version

rem ---- first run: private Python folder for HireMate
if exist ".venv\Scripts\python.exe" goto haveenv
echo  First run: setting things up. This takes 3-5 minutes, only once.
%PY% -m venv .venv >> "%LOG%" 2>&1
if not exist ".venv\Scripts\python.exe" goto fail
:haveenv
set "VPY=%~dp0.venv\Scripts\python.exe"

echo  Installing / checking packages...
"%VPY%" -m pip install --upgrade pip --disable-pip-version-check >> "%LOG%" 2>&1
"%VPY%" -m pip install -r requirements.txt --disable-pip-version-check >> "%LOG%" 2>&1
if errorlevel 1 goto fail
"%VPY%" -m pip install chromadb --disable-pip-version-check >> "%LOG%" 2>&1
if errorlevel 1 echo  ChromaDB skipped - the built-in search store is used. Everything still works.

rem ---- stop an old HireMate that is still running (ports 8000 / 8501 only)
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-NetTCPConnection -LocalPort 8000,8501 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { taskkill /PID $_.OwningProcess /T /F 2>$null | Out-Null }" >nul 2>nul
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do taskkill /PID %%p /T /F >nul 2>nul
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8501 " ^| findstr LISTENING') do taskkill /PID %%p /T /F >nul 2>nul
timeout /t 2 /nobreak >nul

echo  Starting the server...
start "HireMate server - keep open" /min cmd /k ""%VPY%" -m uvicorn backend.app.main:app --port 8000"
set /a N=0
:wait
set /a N+=1
"%VPY%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2)" >nul 2>nul && goto ready
if %N% GEQ 60 goto fail
timeout /t 2 /nobreak >nul
goto wait

:ready
echo  Server is up. >> "%LOG%"
echo.
echo  Opening http://localhost:8501 in your browser.
echo  Sign in: admin@hiremate.demo / recruit123
echo  Keep this window open while you test. Close it to stop HireMate.
start "" http://127.0.0.1:8501
cd frontend
set "API_URL=http://127.0.0.1:8000"
"%VPY%" -m streamlit run app.py --server.port 8501 --server.headless true --server.fileWatcherType none --server.runOnSave false
pause
exit /b 0

:nopython
echo NO PYTHON >> "%LOG%"
echo  Python 3.10 or newer is not installed.
echo  1. Install it from https://www.python.org/downloads/
echo  2. During install, tick "Add python.exe to PATH".
echo  3. Double-click run.bat again.
pause
exit /b 1

:fail
echo FAILED >> "%LOG%"
echo.
echo  Something went wrong. Details are in setup_log.txt in this folder.
pause
exit /b 1
