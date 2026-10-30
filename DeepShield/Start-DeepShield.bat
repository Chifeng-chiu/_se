@echo off
REM ============================================================
REM  DeepShield one-click launcher (double-click the desktop icon)
REM  Usage: double-click = start | Start-DeepShield.bat clean = rebuild venv
REM  Log: DeepShield-startup.log next to this file. Window stays
REM  open on error so you can read the message / share the log.
REM  NOTE: this file must stay pure ASCII (no CJK) for cmd parsing.
REM ============================================================
setlocal
title DeepShield Forensics Engine
cd /d "%~dp0backend"
set LOG=%~dp0DeepShield-startup.log
echo [%date% %time%] ===== DeepShield start ===== > "%LOG%"

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] python not found. Install Python 3.10+ with "Add to PATH".
  echo [ERROR] python not found >> "%LOG%"
  pause
  exit /b 1
)

if /i "%~1"=="clean" (
  echo [CLEAN] Removing old virtualenv...
  rmdir /s /q .venv 2>nul
)

if not exist ".venv\Scripts\python.exe" (
  echo [1/4] Creating virtualenv .venv ...
  python -m venv .venv >> "%LOG%" 2>&1
  if errorlevel 1 (
    echo [ERROR] venv creation failed. See DeepShield-startup.log
    pause
    exit /b 1
  )
)

echo [2/4] Installing core deps (slow on first run)...
echo STEP: core-install-begin >> "%LOG%"
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q -r requirements.txt >> "%LOG%" 2>&1
echo STEP: core-install-exit=%errorlevel% >> "%LOG%"
if errorlevel 1 (
  echo [ERROR] core deps install failed. Check network, see DeepShield-startup.log
  pause
  exit /b 1
)

echo [3/4] Installing optional deps (skipped on failure, harmless)...
echo STEP: opt-install-begin >> "%LOG%"
.venv\Scripts\python.exe -m pip install --disable-pip-version-check -q --only-binary :all: -r requirements-optional.txt >> "%LOG%" 2>&1
echo STEP: opt-install-exit=%errorlevel% >> "%LOG%"
if errorlevel 1 echo [INFO] optional deps skipped - continuing in degraded mode.

REM Kill stale server holding port 8000 (avoids "address already in use")
echo STEP: before-powershell >> "%LOG%"
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Wait-And-Open-Browser.ps1" -Mode kill >> "%LOG%" 2>&1
echo STEP: after-powershell-exit=%errorlevel% >> "%LOG%"
echo STEP: port-clean-done >> "%LOG%"

echo.
echo [4/4] Starting engine at http://localhost:8000 ...
echo   health: http://localhost:8000/api/v1/health
echo   docs:   http://localhost:8000/docs
echo   Browser opens automatically once ready. Close this window to stop.
echo.

REM Background waiter: poll health every 2s, open browser when ready (max 3 min)
start "DeepShieldWaiter" /b powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File "%~dp0Wait-And-Open-Browser.ps1" -Mode wait

echo STEP: pre-uvicorn >> "%LOG%"
.venv\Scripts\python.exe -u -m uvicorn main:app --port 8000 2>&1 | powershell -NoProfile -NonInteractive -Command "$input | Tee-Object -FilePath '%LOG%' -Append"
echo.
echo [STOPPED] Server exited. Full output: DeepShield-startup.log
pause
