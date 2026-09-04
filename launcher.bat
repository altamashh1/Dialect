@echo off
setlocal
title Chat with your data - launcher

REM ---- paths --------------------------------------------------------------
set "ROOT=%~dp0"
set "BACKEND=%ROOT%backend"
set "FRONTEND=%ROOT%frontend"
set "URL=http://localhost:5173"

REM ---- sanity checks ----------------------------------------------------
if not exist "%BACKEND%\.venv\Scripts\python.exe" (
  echo [ERROR] backend venv not found. Run:  cd backend ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -r requirements.txt
  pause
  exit /b 1
)
if not exist "%FRONTEND%\node_modules" (
  echo [ERROR] frontend deps not installed. Run:  cd frontend ^&^& npm install
  pause
  exit /b 1
)

REM ---- start backend (new window) -------------------------------------
echo Starting backend on http://localhost:8000 ...
start "backend - uvicorn" cmd /k "cd /d "%BACKEND%" && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000"

REM ---- start frontend (new window) ----------------------------------
echo Starting frontend on %URL% ...
start "frontend - vite" cmd /k "cd /d "%FRONTEND%" && npm run dev"

REM ---- wait for the frontend to answer, then open Chrome ------------
echo Waiting for the frontend to come up ...
set "READY="
for /l %%i in (1,1,30) do (
  if not defined READY (
    powershell -NoProfile -Command "try { (New-Object Net.Sockets.TcpClient).Connect('localhost',5173); exit 0 } catch { exit 1 }" >nul 2>&1
    if not errorlevel 1 set "READY=1"
    if not defined READY (timeout /t 1 /nobreak >nul)
  )
)

REM ---- find Chrome ---------------------------------------------------
set "CHROME="
for %%p in (
  "%ProgramFiles%\Google\Chrome\Application\chrome.exe"
  "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
  "%LocalAppData%\Google\Chrome\Application\chrome.exe"
) do if not defined CHROME if exist "%%~p" set "CHROME=%%~p"

if defined CHROME (
  echo Opening %URL% in Chrome ...
  start "" "%CHROME%" --new-window "%URL%"
) else (
  echo Chrome not found - opening in your default browser instead.
  start "" "%URL%"
)

echo.
echo Both servers are running in their own windows. Close those windows to stop them.
endlocal
