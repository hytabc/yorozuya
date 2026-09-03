@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "MODE=%~1"
if "%MODE%"=="" set "MODE=start"
if /I not "%MODE%"=="start" if /I not "%MODE%"=="test" goto :usage

set "PYTHON_CMD="
if defined PYTHON_BIN (
    set "PYTHON_CMD="%PYTHON_BIN%""
) else (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYTHON_CMD=py -3"
    if not defined PYTHON_CMD (
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
        if not errorlevel 1 set "PYTHON_CMD=python"
    )
)
if not defined PYTHON_CMD (
    echo Error: Python 3.10 or newer was not found. Set PYTHON_BIN to its executable.
    goto :fail
)
!PYTHON_CMD! -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
if errorlevel 1 (
    echo Error: Python 3.10 or newer is required.
    goto :fail
)

where node >nul 2>&1
if errorlevel 1 (
    echo Error: Node.js was not found. Install Node.js 20.19+ or 22.12+.
    goto :fail
)
where npm >nul 2>&1
if errorlevel 1 (
    echo Error: npm was not found. Install it together with Node.js.
    goto :fail
)
node -e "const [a,b]=process.versions.node.split('.').map(Number); process.exit((a === 20 && b >= 19) || a >= 22 ? 0 : 1)"
if errorlevel 1 (
    echo Error: Node.js 20.19+ or 22.12+ is required.
    goto :fail
)

if not exist "backend\.venv\Scripts\python.exe" (
    echo Creating Python virtual environment...
    !PYTHON_CMD! -m venv "backend\.venv"
    if errorlevel 1 goto :install_fail
) else (
    "backend\.venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
    if errorlevel 1 (
        echo Recreating the virtual environment with a supported Python version...
        !PYTHON_CMD! -m venv --clear "backend\.venv"
        if errorlevel 1 goto :install_fail
    )
)

if "%SKIP_INSTALL%"=="1" goto :dependencies_ready
echo Installing backend dependencies...
"backend\.venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "backend\requirements.txt"
if errorlevel 1 goto :install_fail

echo Installing frontend dependencies...
pushd frontend
call npm install --no-audit --no-fund
set "COMMAND_CODE=!ERRORLEVEL!"
popd
if not "!COMMAND_CODE!"=="0" goto :install_fail

:dependencies_ready
if /I "%MODE%"=="test" goto :test

if not defined WEB_PORT set "WEB_PORT=8080"
if not defined BACKEND_PORT set "BACKEND_PORT=8000"
if not defined DATABASE_URL set "DATABASE_URL=sqlite:///./backend/data/wsw.db"
set "WATCHFILES_FORCE_POLLING=true"
set "VITE_PROXY_TARGET=http://127.0.0.1:%BACKEND_PORT%"

echo Starting backend on http://127.0.0.1:%BACKEND_PORT% ...
start "Yorozuya Backend" /D "%CD%" cmd /k "backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port %BACKEND_PORT% --reload --reload-dir backend\app"
echo Starting frontend on http://127.0.0.1:%WEB_PORT% ...
start "Yorozuya Frontend" /D "%CD%\frontend" cmd /k "npm run dev -- --host 127.0.0.1 --port %WEB_PORT%"
echo.
echo Open http://127.0.0.1:%WEB_PORT% in your browser.
echo Close both newly opened command windows to stop the services.
exit /b 0

:test
echo Running backend tests...
pushd backend
".venv\Scripts\python.exe" -m pytest -q
set "COMMAND_CODE=!ERRORLEVEL!"
popd
if not "!COMMAND_CODE!"=="0" goto :test_fail

echo Building frontend...
pushd frontend
call npm run build
set "COMMAND_CODE=!ERRORLEVEL!"
popd
if not "!COMMAND_CODE!"=="0" goto :test_fail

echo All local checks passed.
exit /b 0

:usage
echo Usage: start.bat [test]
echo   no argument  Install dependencies and start the local development servers
echo   test         Install dependencies, run backend tests and build the frontend
exit /b 2

:install_fail
echo Error: dependency setup failed.
goto :fail

:test_fail
echo Error: local checks failed.

:fail
exit /b 1
