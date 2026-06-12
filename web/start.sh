#!/bin/bash
# Manga Translate Agent Web UI Launcher

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "Starting Manga Translate Agent Web UI..."
echo

# Check if dependencies are installed
if ! python -c "import fastapi" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install fastapi uvicorn sse-starlette
fi

# Start the backend server
echo "Starting backend server on http://127.0.0.1:8000"
python -m uvicorn mga.web.app:create_app --factory --host 127.0.0.1 --port 8000 &

BACKEND_PID=$!

# Wait for server to start
sleep 3

# Open browser
echo "Opening browser..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    open http://127.0.0.1:8000
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    xdg-open http://127.0.0.1:8000
fi

echo
echo "Backend is running at http://127.0.0.1:8000"
echo "Press Ctrl+C to stop the server"
echo

# Wait for interrupt
trap "kill $BACKEND_PID 2>/dev/null; exit" INT TERM
wait $BACKEND_PID