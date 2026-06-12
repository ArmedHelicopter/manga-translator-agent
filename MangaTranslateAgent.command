#!/usr/bin/env bash
# ===========================================================
#  Manga Translate Agent - Desktop Launcher (macOS / Linux)
#  Make executable once:  chmod +x MangaTranslateAgent.command
#  Then double-click (macOS) or run it.
# ===========================================================
set -e
cd "$(dirname "$0")"

# Prefer a bundled virtual environment if present.
PYTHON="python3"
if [ -x ".venv/bin/python" ]; then
    PYTHON=".venv/bin/python"
fi

# First run: build the frontend if it isn't built yet.
if [ ! -f "web/dist/index.html" ]; then
    echo "[Setup] First-time setup, please wait..."
    if command -v npm >/dev/null 2>&1; then
        ( cd web && npm install && npm run build )
    else
        echo "[Warning] npm not found - the rich UI requires a one-time build."
        echo "          Install Node.js, then run this launcher again."
    fi
fi

exec "$PYTHON" -m mga.web.desktop
