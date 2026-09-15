@echo off
setlocal
set "ROOT=%~dp0"

echo ========================================
echo        Starting EGX Platform...
echo ========================================

rem Pull the newest code automatically when Git is available.
where git >nul 2>&1
if not errorlevel 1 (
    echo Checking for updates...
    pushd "%ROOT%"
    git pull --ff-only
    popd
)

rem Start backend only if port 8000 is not already listening.
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul
if errorlevel 1 (
    echo Starting backend...
    start "EGX Backend" /min /D "%ROOT%backend" cmd /k "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
) else (
    echo Backend is already running on port 8000.
)

rem Start frontend only if port 3000 is not already listening.
netstat -ano | findstr ":3000" | findstr "LISTENING" >nul
if errorlevel 1 (
    echo Starting frontend...
    start "EGX Frontend" /min /D "%ROOT%frontend" cmd /k "npm.cmd run dev"
) else (
    echo Frontend is already running on port 3000.
)

echo Waiting for the app to become ready...
timeout /t 6 /nobreak >nul
start "" "http://localhost:3000"

exit
