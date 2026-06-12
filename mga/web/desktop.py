"""Desktop application entrypoint for Manga Translate Agent.

Launches the FastAPI backend in a background thread and opens a native
desktop window (via pywebview) pointing at it. No browser or terminal
interaction is required — double-clicking the launcher is enough.

Usage:
    python -m mga.web.desktop
or via the console script:
    manga-translate-app
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path

import uvicorn

from mga.web.app import create_app

_HOST = "127.0.0.1"
_TITLE = "Manga Translate Agent"


def _find_free_port(host: str = _HOST, preferred: int = 8000) -> int:
    """Return a usable port, preferring 8000 but falling back to a free one."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, preferred))
            return preferred
        except OSError:
            pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        return probe.getsockname()[1]


def _wait_until_ready(host: str, port: int, timeout: float = 30.0) -> bool:
    """Block until the backend accepts TCP connections, or timeout elapses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.settimeout(0.5)
            if probe.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


def _run_server(host: str, port: int, project_root: Path) -> None:
    app = create_app(project_root=project_root)
    uvicorn.run(app, host=host, port=port, log_level="warning")


def _icon_path() -> Path | None:
    """Locate the platform-appropriate window icon, if available.

    Honours ``MGA_ICON_DIR`` (set by packaged builds) and otherwise looks in
    ``web/dist-icons`` relative to the repo root. Prefers PNG for the window
    (broadest pywebview backend support), then ICO.
    """
    import os
    import sys

    search_dirs: list[Path] = []
    env_dir = os.getenv("MGA_ICON_DIR")
    if env_dir:
        search_dirs.append(Path(env_dir))
    # When frozen by PyInstaller, bundled data lives under sys._MEIPASS.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        search_dirs.append(Path(meipass) / "icons")
    search_dirs.append(Path(__file__).resolve().parents[2] / "web" / "dist-icons")

    preferred = ["icon.png", "icon.ico"]
    if sys.platform == "win32":
        preferred = ["icon.ico", "icon.png"]

    for directory in search_dirs:
        for name in preferred:
            candidate = directory / name
            if candidate.is_file():
                return candidate
    return None


def main(project_root: str | Path | None = None) -> None:
    """Start the backend and open the desktop window."""
    # Default project root: a stable per-user data directory so projects persist
    # across launches regardless of the working directory.
    if project_root is None:
        project_root = Path.home() / "MangaTranslateAgent" / "projects"
    project_root = Path(project_root)
    project_root.mkdir(parents=True, exist_ok=True)

    port = _find_free_port()

    server_thread = threading.Thread(
        target=_run_server,
        args=(_HOST, port, project_root),
        daemon=True,
    )
    server_thread.start()

    if not _wait_until_ready(_HOST, port):
        raise RuntimeError(
            f"Backend failed to start on {_HOST}:{port} within the timeout."
        )

    url = f"http://{_HOST}:{port}"

    # Headless / server-only mode: keep the backend running without opening a
    # native window. Useful for debugging, CI, and advanced users who prefer
    # their own browser. Enabled via MGA_SERVER_ONLY=1.
    import os

    if os.getenv("MGA_SERVER_ONLY") == "1":
        print(f"[mga] Server-only mode. Open {url} in your browser.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        return

    try:
        import webview  # pywebview

        window_kwargs: dict = dict(width=1280, height=820, min_size=(960, 640))

        # Apply the app icon when the active GUI backend supports it.
        icon_path = _icon_path()
        if icon_path is not None:
            window_kwargs["icon"] = str(icon_path)

        try:
            webview.create_window(_TITLE, url, **window_kwargs)
        except TypeError:
            # Older pywebview signatures don't accept ``icon``; retry without it.
            window_kwargs.pop("icon", None)
            webview.create_window(_TITLE, url, **window_kwargs)
        webview.start()
    except ImportError:
        # Graceful fallback: if pywebview isn't installed, open the default
        # browser so the app is still usable.
        import webbrowser

        print(f"[mga] pywebview not installed; opening {url} in your browser.")
        print("[mga] Install the desktop window with: pip install pywebview")
        webbrowser.open(url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
