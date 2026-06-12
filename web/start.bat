@echo off
REM Manga Translate Agent Web UI Launcher

cd /d "%~dp0\.."

echo Starting Manga Translate Agent Web UI...
echo.

REM Check if dependencies are installed
python -c "import fastapi" 2>nul
if errorlevel 1 (
    echo Installing dependencies...
    pip install fastapi uvicorn sse-starlette
)

REM Start the backend server
echo Starting backend server on http://127.0.0.1:8000
start "Manga Translate Agent" python -m uvicorn mga.web.app:create_app --factory --host 127.0.0.1 --port 8000

REM Wait for server to start
timeout /t 3 /nobreak > nul

REM Open browser
echo Opening browser...
start http://127.0.0.1:8000

echo.
echo Backend is running at http://127.0.0.1:8000
echo Press Ctrl+C to stop the server
echo.