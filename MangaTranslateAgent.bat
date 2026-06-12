@echo off
REM ===========================================================
REM  Manga Translate Agent - Desktop Launcher (Windows)
REM  Double-click this file to start the app. No command line
REM  knowledge required.
REM ===========================================================

cd /d "%~dp0"

REM Prefer a bundled virtual environment if present, else system Python.
set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"

REM First run: ensure the frontend is built and deps are installed.
if not exist "web\dist\index.html" (
    echo [Setup] First-time setup, please wait...
    where npm >nul 2>nul
    if %errorlevel%==0 (
        pushd web
        call npm install
        call npm run build
        popd
    ) else (
        echo [Warning] npm not found - the rich UI requires a one-time build.
        echo            Install Node.js, then run this launcher again.
    )
)

"%PYTHON%" -m mga.web.desktop
if %errorlevel% neq 0 (
    echo.
    echo [Error] The application exited unexpectedly.
    pause
)
