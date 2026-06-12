# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Manga Translate Agent desktop shell.

Builds a THIN bundle: only the management UI stack (FastAPI / uvicorn /
pywebview) plus the built frontend and icons. The heavy ML engine
(torch, transformers, manga-ocr, ...) is deliberately EXCLUDED and is
installed online on first use via the in-app "Install Engine" flow.

Build:
    pyinstaller MangaTranslateAgent.spec --noconfirm

Output:
    dist/MangaTranslateAgent/        (onedir; ship the whole folder)
"""

import sys
from pathlib import Path

block_cipher = None

ROOT = Path(SPECPATH)
FRONTEND_DIST = ROOT / "web" / "dist"
ICON_DIR = ROOT / "web" / "dist-icons"

if not (FRONTEND_DIST / "index.html").is_file():
    raise SystemExit(
        "web/dist/index.html not found. Build the frontend first:\n"
        "    cd web && npm install && npm run build"
    )

# Bundle the built frontend and icons as data so the frozen app can serve them.
datas = [
    (str(FRONTEND_DIST), "web/dist"),
    (str(ICON_DIR), "icons"),
]

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "sse_starlette",
    "sse_starlette.sse",
]

# Keep the bundle thin: the heavy ML/data stack is installed online at runtime.
excludes = [
    "torch", "torchvision", "torchaudio",
    "transformers", "manga_ocr", "manga_translator",
    "cv2", "onnxruntime", "open_clip", "einops",
    "pandas", "scipy", "sklearn", "matplotlib",
    "tensorflow", "jax",
    "IPython", "notebook", "ipykernel",
]

win_icon = str(ICON_DIR / "icon.ico") if (ICON_DIR / "icon.ico").is_file() else None
mac_icon = str(ICON_DIR / "icon.icns") if (ICON_DIR / "icon.icns").is_file() else None

a = Analysis(
    ["mga/web/desktop.py"],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MangaTranslateAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,            # windowed app, no terminal
    disable_windowed_traceback=False,
    icon=win_icon or mac_icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MangaTranslateAgent",
)

# Produce a macOS .app bundle when building on macOS.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="MangaTranslateAgent.app",
        icon=mac_icon,
        bundle_identifier="com.mangatranslate.agent",
    )
