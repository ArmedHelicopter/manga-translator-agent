"""On-demand installation of the heavy translation-engine dependencies.

The desktop shell ships thin: it only needs FastAPI / uvicorn / pywebview to
run the management UI. The heavy ML stack (torch, transformers, manga-ocr,
opencv, ...) is only required to actually run a translation, so we install it
online on first use and stream progress to the UI.

Public surface used by the web API:
    engine_status()      -> dict describing which deps are present / missing
    install_engine(...)  -> generator yielding progress log lines (for SSE)
"""

from __future__ import annotations

import importlib.util
import os
import site
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


def _is_frozen() -> bool:
    """True when running inside a PyInstaller bundle."""
    return getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")


def _engine_site_dir() -> Path:
    """User-writable directory where engine deps are installed when frozen.

    A frozen bundle's interpreter has no writable site-packages, so we install
    into a stable per-user location and add it to ``sys.path`` (and the
    ``PYTHONPATH`` handed to any subprocess runtime).
    """
    base = os.getenv("MGA_ENGINE_DIR")
    if base:
        return Path(base)
    return Path.home() / "MangaTranslateAgent" / "engine"


def _python_executable() -> str:
    """Return a real Python interpreter usable for ``pip install``.

    When frozen, ``sys.executable`` is the bundled app (not Python), so we look
    for a system interpreter instead.
    """
    if not _is_frozen():
        return sys.executable

    import shutil

    for name in ("python3", "python"):
        found = shutil.which(name)
        if found:
            return found
    # Last resort: hope the bundle's executable understands -m pip (it won't in
    # most cases, but surfacing a clear error downstream is better than guessing).
    return sys.executable


def _ensure_engine_dir_on_path() -> Path | None:
    """Make a previously-installed engine dir importable. Returns the dir if used."""
    if not _is_frozen():
        return None
    target = _engine_site_dir()
    if target.is_dir():
        target_str = str(target)
        if target_str not in sys.path:
            site.addsitedir(target_str)
        existing = os.environ.get("PYTHONPATH", "")
        if target_str not in existing.split(os.pathsep):
            os.environ["PYTHONPATH"] = (
                target_str + (os.pathsep + existing if existing else "")
            )
    return target


# Make any prior install visible as soon as this module is imported.
_ensure_engine_dir_on_path()


@dataclass(frozen=True)
class EngineDependency:
    """A pip requirement plus the module used to detect its presence."""

    requirement: str   # what we pass to pip
    import_name: str   # what we import to check installation
    label: str         # human-friendly name for the UI


# Ordered so the largest / most fundamental wheels come first.
ENGINE_DEPENDENCIES: tuple[EngineDependency, ...] = (
    EngineDependency("torch", "torch", "PyTorch"),
    EngineDependency("torchvision", "torchvision", "TorchVision"),
    EngineDependency("transformers", "transformers", "Transformers"),
    EngineDependency("opencv-python", "cv2", "OpenCV"),
    EngineDependency("onnxruntime", "onnxruntime", "ONNX Runtime"),
    EngineDependency("manga-ocr", "manga_ocr", "Manga OCR"),
    EngineDependency("open_clip_torch", "open_clip", "OpenCLIP"),
    EngineDependency("einops", "einops", "einops"),
    EngineDependency("rusty-manga-image-translator", "manga_translator", "Manga Image Translator runtime"),
)


def _is_installed(import_name: str) -> bool:
    try:
        return importlib.util.find_spec(import_name) is not None
    except (ImportError, ValueError):
        return False


def engine_status() -> dict:
    """Return which engine dependencies are installed vs missing."""
    deps = []
    for dep in ENGINE_DEPENDENCIES:
        installed = _is_installed(dep.import_name)
        deps.append(
            {
                "requirement": dep.requirement,
                "label": dep.label,
                "installed": installed,
            }
        )
    missing = [d for d in deps if not d["installed"]]
    return {
        "ready": len(missing) == 0,
        "dependencies": deps,
        "missing_count": len(missing),
        "total_count": len(deps),
    }


def _missing_requirements() -> list[str]:
    return [
        dep.requirement
        for dep in ENGINE_DEPENDENCIES
        if not _is_installed(dep.import_name)
    ]


def install_engine(extra_index_url: str | None = None) -> Iterator[str]:
    """Install all missing engine deps, yielding pip output lines.

    Designed to back a Server-Sent-Events stream so the UI can show live
    progress. Yields plain strings; the final line is a sentinel beginning
    with ``__DONE__`` or ``__ERROR__``.
    """
    missing = _missing_requirements()
    if not missing:
        yield "All engine dependencies are already installed."
        yield "__DONE__"
        return

    yield f"Installing {len(missing)} package(s): {', '.join(missing)}"
    yield "This is a one-time download and may take several minutes..."

    python_exe = _python_executable()
    cmd = [python_exe, "-m", "pip", "install", "--upgrade"]

    # When frozen, install into a user-writable engine dir and expose it on the
    # import path so the freshly installed packages become usable immediately.
    target_dir: Path | None = None
    if _is_frozen():
        target_dir = _engine_site_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        cmd.extend(["--target", str(target_dir)])

    cmd.extend(missing)
    if extra_index_url:
        cmd.extend(["--extra-index-url", extra_index_url])

    yield f"$ {' '.join(cmd)}"

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError as exc:  # pragma: no cover - pip should always exist
        yield f"Failed to launch pip: {exc}"
        yield "__ERROR__"
        return

    assert proc.stdout is not None
    for line in proc.stdout:
        yield line.rstrip("\n")

    code = proc.wait()
    if code != 0:
        yield f"pip exited with status {code}"
        yield "__ERROR__"
        return

    # Re-check; importlib caches may need clearing for freshly installed pkgs.
    if target_dir is not None:
        _ensure_engine_dir_on_path()
    importlib.invalidate_caches()
    still_missing = _missing_requirements()
    if still_missing:
        yield f"Still missing after install: {', '.join(still_missing)}"
        yield "__ERROR__"
        return

    yield "Engine dependencies installed successfully."
    yield "__DONE__"
