# Manga Translate Agent - Desktop Distribution Guide

## Three Ways to Run

### 1. 🚀 Double-Click Launcher (Recommended for Development)

**Windows**: Double-click `MangaTranslateAgent.bat`  
**macOS/Linux**: `chmod +x MangaTranslateAgent.command && ./MangaTranslateAgent.command`

**What happens**:
- Checks if frontend is built; if not, runs `npm install && npm run build` (requires Node.js)
- Starts the FastAPI backend
- Opens a native desktop window (via pywebview)
- No browser or command line needed

**Requirements**:
- Python 3.10-3.12 with dependencies: `pip install -e ".[dev]"`
- Node.js (for first-run frontend build only)
- `pip install pywebview` for native window (falls back to browser if missing)

---

### 2. 📦 Frozen Executable (End Users)

**Build once**:
```bash
pip install pyinstaller
python -m mga.web.make_icon  # generate icon
cd web && npm install && npm run build && cd ..
pyinstaller MangaTranslateAgent.spec
```

**Distribute**: `dist-app/MangaTranslateAgent/` folder (~140 MB)

**Run**: Double-click `MangaTranslateAgent.exe`

**Key features**:
- No Python installation required (bundled)
- Opens native window instantly
- **Thin shell**: Heavy ML deps (torch, 5+ GB) NOT bundled
- **On-demand install**: First translation triggers one-click online install with live progress
- Projects persist in `~/MangaTranslateAgent/projects/`

---

### 3. 🔧 Command Mode (Advanced)

```bash
manga-translate-app  # or: python -m mga.web.desktop
MGA_SERVER_ONLY=1 python -m mga.web.desktop  # server-only, open http://127.0.0.1:8000
```

---

## On-Demand Engine Install

Frozen bundle is **thin** (140 MB) by excluding torch/transformers/opencv (~5 GB).

**User flow**:
1. Download 140 MB zip → extract → double-click exe → window opens
2. All management UI works (projects, characters, terms, providers)
3. Click "Start Translation" → setup screen: "Engine not installed. Download now? (~5 GB)"
4. Click → live pip install log → done in 5-10 min
5. Translate forever

**What gets installed**: `pip install torch torchvision transformers opencv-python onnxruntime manga-ocr open_clip_torch einops rusty-manga-image-translator`

**Install location**: `~/MangaTranslateAgent/engine/` (auto-added to sys.path)

---

## Icon

Blue rounded square with white "M":

```bash
python -m mga.web.make_icon  # → web/dist-icons/icon.{png,ico,icns}
```

---

## Full Build Checklist

```bash
# 1. Install tools
pip install pyinstaller pillow
cd web && npm install && cd ..

# 2. Generate icon
python -m mga.web.make_icon

# 3. Build frontend
cd web && npm run build && cd ..

# 4. Build frozen bundle
pyinstaller MangaTranslateAgent.spec --noconfirm

# 5. Test
dist-app/MangaTranslateAgent/MangaTranslateAgent.exe

# 6. Package
cd dist-app && zip -r MangaTranslateAgent-Windows.zip MangaTranslateAgent/
```

---

## FAQ

**Q: Why 140 MB if deps aren't bundled?**  
A: Python + FastAPI + React + pywebview + numpy/Pillow. Torch alone is 2+ GB.

**Q: Offline install?**  
A: Pre-install engine deps, copy `~/MangaTranslateAgent/engine/` into distribution, set `MGA_ENGINE_DIR=./engine`.

**Q: Why pywebview vs Electron?**  
A: Uses OS native WebView (Edge WebView2/WKWebView), no 100+ MB Chromium.

---

**Result**: One-click desktop app, no command-line friction, smart on-demand install. 🎉
