#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT_SOURCE_DIR="${INPUT_SOURCE_DIR:-$ROOT_DIR/data/sources/real_pages/test}"
WORK_INPUT_DIR="${WORK_INPUT_DIR:-$ROOT_DIR/data/samples/external_review_input}"
INTERNAL_OUT_DIR="${INTERNAL_OUT_DIR:-$ROOT_DIR/data/runs/external/review_internal}"
EXTERNAL_OUT_DIR="${EXTERNAL_OUT_DIR:-$ROOT_DIR/data/runs/external/review_external}"
REVIEW_OUT_DIR="${REVIEW_OUT_DIR:-$ROOT_DIR/data/reviews/external_review}"
COUNT="${COUNT:-5}"
START_INDEX="${START_INDEX:-0}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.main-cli-venv/bin/python}"
EXTERNAL_PYTHON="${EXTERNAL_PYTHON:-$ROOT_DIR/.external-mit-venv/bin/python}"
REPO_DIR="${REPO_DIR:-$ROOT_DIR/external/external/manga-image-translator}"
HEARTBEAT_SECONDS="${HEARTBEAT_SECONDS:-30}"
SKIP_INTERNAL="${SKIP_INTERNAL:-0}"
SKIP_EXTERNAL="${SKIP_EXTERNAL:-0}"

log() {
  printf '\n[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

require_file() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "Expected file missing: $path" >&2
    exit 1
  fi
}

require_dir() {
  local path="$1"
  if [[ ! -d "$path" ]]; then
    echo "Expected directory missing: $path" >&2
    exit 1
  fi
}

count_files() {
  local path="$1"
  if [[ ! -d "$path" ]]; then
    echo "0"
    return
  fi
  find "$path" -type f | wc -l | tr -d ' '
}

count_external_markers() {
  local path="$1"
  if [[ ! -f "$path" ]]; then
    echo "0"
    return
  fi
  grep -c '^\[' "$path" || true
}

provider_preflight() {
  log "Running provider connectivity preflight"
  export ROOT_DIR PYTHON_BIN
  "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(os.environ["ROOT_DIR"])
sys.path.insert(0, str(ROOT / "src"))

from manga_translate.config.loader import load_provider_settings
from manga_translate.providers import build_provider

raw = load_provider_settings()
provider = build_provider(raw, "openai")

try:
    response_json, elapsed_ms = provider._post(  # noqa: SLF001
        {
            "model": raw["providers"]["openai"].get("text_model", "gpt-4o-mini"),
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": "Return valid JSON."},
                {"role": "user", "content": '{"ok": true, "kind": "preflight"}'},
            ],
            "max_tokens": 32,
        }
    )
except Exception as exc:  # pragma: no cover - shell preflight path
    print(f"Provider preflight failed: {exc}", file=sys.stderr)
    raise SystemExit(1) from exc

choice_count = len(response_json.get("choices", [])) if isinstance(response_json, dict) else 0
print(
    f"Provider preflight OK: base_url={raw['providers']['openai'].get('base_url')} "
    f"text_model={raw['providers']['openai'].get('text_model')} "
    f"choices={choice_count} latency_ms={elapsed_ms}"
)
PY
}

heartbeat() {
  while true; do
    sleep "$HEARTBEAT_SECONDS"
    local internal_files external_files review_files marker_count
    internal_files="$(count_files "$INTERNAL_OUT_DIR")"
    external_files="$(count_files "$EXTERNAL_OUT_DIR")"
    review_files="$(count_files "$REVIEW_OUT_DIR")"
    marker_count="$(count_external_markers "$EXTERNAL_OUT_DIR/external-baseline-text.txt")"
    log "Heartbeat: external markers=$marker_count, files internal=$internal_files external=$external_files review=$review_files"
  done
}

mkdir -p "$WORK_INPUT_DIR"
rm -rf "$WORK_INPUT_DIR"/*
rm -rf "$INTERNAL_OUT_DIR" "$EXTERNAL_OUT_DIR" "$REVIEW_OUT_DIR"

heartbeat &
HEARTBEAT_PID=$!
cleanup() {
  if [[ -n "${HEARTBEAT_PID:-}" ]]; then
    kill "$HEARTBEAT_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

log "Preparing contiguous sample window"
export ROOT_DIR WORK_INPUT_DIR INPUT_SOURCE_DIR COUNT START_INDEX
python3 - <<'PY'
from pathlib import Path
import os
import shutil

src = Path(os.environ["INPUT_SOURCE_DIR"])
dst = Path(os.environ["WORK_INPUT_DIR"])
count = int(os.environ["COUNT"])
start = int(os.environ["START_INDEX"])

files = sorted(src.glob("*.jpg"))
selected = files[start:start + count]
if len(selected) < count:
    raise SystemExit(f"Not enough source pages in {src}; requested {count} from index {start}, got {len(selected)}")

for i, src_path in enumerate(selected, start=1):
    out_path = dst / f"{i:03d}.jpg"
    shutil.copy2(src_path, out_path)
    print(f"{out_path.name} <- {src_path.name}")
PY

require_dir "$WORK_INPUT_DIR"
sample_count=$(find "$WORK_INPUT_DIR" -maxdepth 1 -type f | wc -l | tr -d ' ')
log "Prepared $sample_count input file(s) in $WORK_INPUT_DIR"

cd "$ROOT_DIR"

if [[ "$SKIP_INTERNAL" != "1" ]]; then
  provider_preflight

  log "Running internal benchmark-extraction"
  PYTHONPATH=src "$PYTHON_BIN" -m manga_translate.cli benchmark-extraction \
    "$WORK_INPUT_DIR" \
    -o "$INTERNAL_OUT_DIR" \
    --sample-size "$COUNT" \
    --sample-start 0 \
    --vision-mode structured \
    --vision-mode direct \
    --ocr-spec tesseract_jpn \
    --ocr-spec tesseract_jpn_vert \
    --ocr-spec tesseract_jpn+eng

  require_file "$INTERNAL_OUT_DIR/benchmark/run.json"
  require_file "$INTERNAL_OUT_DIR/benchmark/translation-report.json"
  log "Internal benchmark completed"
else
  log "Skipping internal benchmark-extraction because SKIP_INTERNAL=1"
fi

if [[ "$SKIP_EXTERNAL" != "1" ]]; then
  log "Running external benchmark-external"
  MANGA_TRANSLATE_EXTERNAL_PYTHON="$EXTERNAL_PYTHON" \
  PYTHONPATH=src \
  "$PYTHON_BIN" -m manga_translate.cli benchmark-external \
    "$WORK_INPUT_DIR" \
    -o "$EXTERNAL_OUT_DIR" \
    --repo-dir "$REPO_DIR" \
    --compare-with-internal

  require_file "$EXTERNAL_OUT_DIR/benchmark/run.json"
  require_file "$EXTERNAL_OUT_DIR/benchmark/external-translation-report.json"
  require_file "$EXTERNAL_OUT_DIR/external-baseline-text-normalized.json"
  log "External benchmark completed"
else
  log "Skipping external benchmark-external because SKIP_EXTERNAL=1"
fi

if [[ "$SKIP_INTERNAL" != "1" && "$SKIP_EXTERNAL" != "1" ]]; then
  log "Assembling review directory"
  MTA_INTERNAL_DIR="$INTERNAL_OUT_DIR" \
  MTA_EXTERNAL_DIR="$EXTERNAL_OUT_DIR" \
  MTA_REVIEW_DIR="$REVIEW_OUT_DIR" \
  python3 "$ROOT_DIR/scripts/assemble_external_smoke_review.py"

  require_file "$REVIEW_OUT_DIR/README.md"
  log "Review assembly completed"
else
  log "Skipping review assembly because one of the benchmark stages was skipped"
fi

echo
echo "Done."
echo "Input sample dir: $WORK_INPUT_DIR"
echo "Internal artifacts: $INTERNAL_OUT_DIR"
echo "External artifacts: $EXTERNAL_OUT_DIR"
if [[ "$SKIP_INTERNAL" != "1" && "$SKIP_EXTERNAL" != "1" ]]; then
  echo "Review overview: $REVIEW_OUT_DIR/README.md"
fi
