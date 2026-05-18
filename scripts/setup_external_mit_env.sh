#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-$ROOT_DIR/.external-mit-venv}"
REPO_DIR="${REPO_DIR:-$ROOT_DIR/external/external/manga-image-translator}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
RUST_WHEEL_INDEX="https://frederik-uni.github.io/manga-image-translator-rust/python/wheels/simple/"
PYDENSECRF_GIT="git+https://github.com/lucasb-eyer/pydensecrf.git"

if [[ ! -d "$REPO_DIR" ]]; then
  echo "External repo not found: $REPO_DIR" >&2
  echo "Clone manga-image-translator into external/external/manga-image-translator first." >&2
  exit 1
fi

"$PYTHON_BIN" -m venv "$VENV_DIR"
source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip setuptools wheel

# Install the heaviest and most conflict-prone packages first so later syncs are cheaper.
python -m pip install \
  --extra-index-url "$RUST_WHEEL_INDEX" \
  "numpy==1.26.4" \
  "openai==1.63.0" \
  "httpx==0.27.2" \
  "pydantic==2.5.0" \
  "protobuf>=3.20.2,<6.0.0" \
  torch \
  torchvision \
  opencv-python \
  onnxruntime \
  transformers \
  ctranslate2 \
  timm \
  open_clip_torch \
  huggingface_hub \
  safetensors \
  pandas \
  google-genai \
  groq \
  manga-ocr \
  rusty-manga-image-translator

# Match the upstream project dependency source for pydensecrf.
python -m pip install "$PYDENSECRF_GIT"

# Finish by syncing the upstream requirements file. This can still be slow, but should
# now mostly reuse the pinned/preinstalled packages above instead of full backtracking.
python -m pip install -r "$REPO_DIR/requirements.txt"

cat <<EOF
External baseline environment is ready.

Activate:
  source "$VENV_DIR/bin/activate"

Run smoke benchmark:
  MANGA_TRANSLATE_EXTERNAL_PYTHON="$VENV_DIR/bin/python" \\
  PYTHONPATH=src python -m manga_translate.cli benchmark-external \\
    data/samples/external_smoke_input \\
    -o data/runs/external/smoke_external \\
    --repo-dir external/external/manga-image-translator
EOF
