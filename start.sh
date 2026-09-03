#!/bin/sh

set -u

ROOT_DIR=$(CDPATH= cd -P "$(dirname "$0")" && pwd)
MODE=${1:-start}

usage() {
    echo "Usage: ./start.sh [test]"
    echo "  no argument  Install dependencies and start the local development servers"
    echo "  test         Install dependencies, run backend tests and build the frontend"
}

fail() {
    echo "Error: $1" >&2
    exit 1
}

if [ "$MODE" != "start" ] && [ "$MODE" != "test" ]; then
    usage
    exit 2
fi

python_supported() {
    "$1" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1
}

PYTHON_CMD=${PYTHON_BIN:-}
if [ -n "$PYTHON_CMD" ]; then
    command -v "$PYTHON_CMD" >/dev/null 2>&1 || fail "PYTHON_BIN does not point to an executable command: $PYTHON_CMD"
    python_supported "$PYTHON_CMD" || fail "Python 3.10 or newer is required."
else
    for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 && python_supported "$candidate"; then
            PYTHON_CMD=$candidate
            break
        fi
    done
    [ -n "$PYTHON_CMD" ] || fail "Python 3.10 or newer was not found. Set PYTHON_BIN to its executable."
fi

command -v node >/dev/null 2>&1 || fail "Node.js was not found. Install Node.js 20.19+ or 22.12+."
command -v npm >/dev/null 2>&1 || fail "npm was not found. Install it together with Node.js."
node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit((a === 20 && b >= 19) || a >= 22 ? 0 : 1)' \
    || fail "Node.js 20.19+ or 22.12+ is required."

VENV_PYTHON="$ROOT_DIR/backend/.venv/bin/python"
if [ ! -x "$VENV_PYTHON" ]; then
    echo "Creating Python virtual environment..."
    "$PYTHON_CMD" -m venv "$ROOT_DIR/backend/.venv" || fail "Could not create the Python virtual environment."
elif ! "$VENV_PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
    echo "Recreating the virtual environment with a supported Python version..."
    "$PYTHON_CMD" -m venv --clear "$ROOT_DIR/backend/.venv" || fail "Could not recreate the Python virtual environment."
fi

if [ "${SKIP_INSTALL:-0}" != "1" ]; then
    echo "Installing backend dependencies..."
    "$VENV_PYTHON" -m pip install --disable-pip-version-check -r "$ROOT_DIR/backend/requirements.txt" \
        || fail "Backend dependency installation failed."

    echo "Installing frontend dependencies..."
    (cd "$ROOT_DIR/frontend" && npm install --no-audit --no-fund) \
        || fail "Frontend dependency installation failed."
fi

if [ "$MODE" = "test" ]; then
    echo "Running backend tests..."
    (cd "$ROOT_DIR/backend" && .venv/bin/python -m pytest -q) || fail "Backend tests failed."

    echo "Building frontend..."
    (cd "$ROOT_DIR/frontend" && npm run build) || fail "Frontend build failed."

    echo "All local checks passed."
    exit 0
fi

WEB_PORT=${WEB_PORT:-8080}
BACKEND_PORT=${BACKEND_PORT:-8000}
case "$WEB_PORT:$BACKEND_PORT" in
    *[!0-9:]*) fail "WEB_PORT and BACKEND_PORT must be numeric." ;;
esac

BACKEND_PID=
FRONTEND_PID=
stop_services() {
    trap - INT TERM EXIT
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
    [ -n "$FRONTEND_PID" ] && wait "$FRONTEND_PID" 2>/dev/null || true
    [ -n "$BACKEND_PID" ] && wait "$BACKEND_PID" 2>/dev/null || true
}
trap 'stop_services; exit 130' INT TERM
trap stop_services EXIT

echo "Starting backend on http://127.0.0.1:$BACKEND_PORT ..."
(
    cd "$ROOT_DIR" || exit 1
    export DATABASE_URL=${DATABASE_URL:-sqlite:///./backend/data/wsw.db}
    export WATCHFILES_FORCE_POLLING=true
    exec "$VENV_PYTHON" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port "$BACKEND_PORT" --reload --reload-dir backend/app
) &
BACKEND_PID=$!

echo "Starting frontend on http://127.0.0.1:$WEB_PORT ..."
(
    cd "$ROOT_DIR/frontend" || exit 1
    export VITE_PROXY_TARGET="http://127.0.0.1:$BACKEND_PORT"
    exec npm run dev -- --host 127.0.0.1 --port "$WEB_PORT"
) &
FRONTEND_PID=$!

echo "Open http://127.0.0.1:$WEB_PORT in your browser. Press Ctrl+C to stop both services."
while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
    sleep 1
done

fail "A local service stopped unexpectedly. Check the output above."
