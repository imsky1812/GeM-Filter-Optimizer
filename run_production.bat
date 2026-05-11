@echo off
SETLOCAL EnableDelayedExpansion
TITLE GeM Filter Optimizer Installer

echo =========================================
echo    GeM Filter Optimizer - Production
echo =========================================
echo.

cd /d "%~dp0"

:: Step 1: Check Frontend
echo [1/4] Preparing Frontend UI...
cd frontend
if not exist node_modules (
    echo Installing node modules (first time setup)...
    call npm install
)
echo Building production web client...
call npm run build
cd ..

:: Step 2: Setup Python Backend
echo.
echo [2/4] Preparing Python Core...
cd backend
if not exist venv (
    echo Creating local python virtual environment...
    python -m venv venv
)
call venv\Scripts\activate
echo Installing server dependencies...
pip install -r requirements.txt --quiet
cd ..

:: Step 3: Ready notification and Browser start
echo.
echo [3/4] Configuration complete.
echo Starting application engine...
timeout /t 2 > nul
start "" "http://localhost:8000"

:: Step 4: Launch Uvicorn
echo [4/4] Launching Server...
echo ------------------------------------------
echo Application Running at http://localhost:8000
echo KEEP THIS WINDOW OPEN TO USE THE TOOL
echo Press CTRL+C to close the server.
echo ------------------------------------------
cd backend
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2
pause
