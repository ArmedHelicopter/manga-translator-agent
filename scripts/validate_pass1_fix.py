#!/usr/bin/env python3
"""Validate Pass 1 export-artifact output for the runtime bridge fix.

The script looks for a 10-page sample input under experiments/ by default,
runs the runtime bridge export-artifact pass, and prints summary metrics useful
for manual validation.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAYLOAD_DIR = ROOT / "data" / "experiments" / "pass1-fix-validation" / ".mga-payload"
DEFAULT_INPUT_NAMES = (
    "run-2026-06-07-10pages",
    "run-2026-06-07-10-pages",
    "run-2026-06-07_10pages",
    "sample-10pages",
    "sample-10-pages",
    "10pages",
    "10-pages",
)

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _has_image_input(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_file():
        return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".pdf", ".cbz", ".cbr", ".epub"}
    image_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    return any(child.is_file() and child.suffix.lower() in image_exts for child in path.rglob("*"))


def find_default_input() -> tuple[Path | None, list[Path]]:
    experiments_dir = ROOT / "data" / "experiments"
    candidates = [experiments_dir / name for name in DEFAULT_INPUT_NAMES]

    if experiments_dir.exists():
        for child in sorted(experiments_dir.iterdir()):
            lowered = child.name.lower()
            if "10" in lowered and "page" in lowered:
                candidates.append(child)

    existing = _unique_paths([path for path in candidates if _has_image_input(path)])
    return (existing[0] if existing else None), existing


def artifact_paths(payload_dir: Path) -> list[Path]:
    per_page = sorted(payload_dir.glob("artifact-*.json"))
    if per_page:
        return per_page
    single = payload_dir / "artifact.json"
    return [single] if single.exists() else []


def collect_metrics(payload_dir: Path, export_result: dict[str, Any]) -> dict[str, Any]:
    artifacts = artifact_paths(payload_dir)
    text_region_count = 0
    pages_with_text_regions = 0
    empty_text_region_pages = 0

    for artifact_path in artifacts:
        try:
            artifact = _load_json(artifact_path)
        except (json.JSONDecodeError, OSError):
            continue
        regions = artifact.get("text_regions", [])
        if not isinstance(regions, list):
            continue
        text_region_count += len(regions)
        if regions:
            pages_with_text_regions += 1
        else:
            empty_text_region_pages += 1

    fallback_count = int(export_result.get("fallback_page_count", 0) or 0)
    fallback_manifest_path = payload_dir / "fallback-pages.json"
    if fallback_manifest_path.exists():
        try:
            fallback_manifest = _load_json(fallback_manifest_path)
            fallback_count = int(fallback_manifest.get("fallback_page_count", fallback_count) or 0)
        except (json.JSONDecodeError, OSError, ValueError, TypeError):
            pass

    pages_manifest_path = payload_dir / "pages.json"
    page_count = None
    if pages_manifest_path.exists():
        try:
            pages_manifest = _load_json(pages_manifest_path)
            if isinstance(pages_manifest, list):
                page_count = len(pages_manifest)
        except (json.JSONDecodeError, OSError):
            page_count = None

    metrics = {
        "payload_dir": str(payload_dir.resolve()),
        "page_count": page_count,
        "expected_page_count": export_result.get("expected_page_count"),
        "artifact_count": len(artifacts),
        "text_regions_count": text_region_count,
        "pages_with_text_regions": pages_with_text_regions,
        "empty_text_region_pages": empty_text_region_pages,
        "fallback_count": fallback_count,
        "fallback_page_indices": export_result.get("fallback_page_indices", []),
        "ocr_model": export_result.get("ocr_model"),
        "returncode": export_result.get("returncode"),
    }
    return metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Pass 1 export-artifact output on a 10-page sample.")
    parser.add_argument(
        "--input",
        dest="input_path",
        type=Path,
        default=None,
        help="Sample input path. Defaults to data/experiments/run-2026-06-07-10pages or a similar 10-page path.",
    )
    parser.add_argument(
        "--payload-dir",
        type=Path,
        default=DEFAULT_PAYLOAD_DIR,
        help=f"Payload output directory. Default: {DEFAULT_PAYLOAD_DIR}",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=10,
        help="Maximum pages requested from the bridge for validation. Default: 10.",
    )
    parser.add_argument(
        "--ocr-model",
        default="48px",
        help="OCR model passed to run_export_artifact. Default: 48px.",
    )
    parser.add_argument(
        "--reuse",
        action="store_true",
        help="Reuse an existing payload directory instead of deleting it before validation.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    default_input, discovered_inputs = find_default_input()
    input_path = args.input_path or default_input

    if input_path is None or not _has_image_input(input_path):
        print("No usable 10-page validation input was found.", file=sys.stderr)
        print("Checked these default/similar candidates:", file=sys.stderr)
        for candidate in discovered_inputs or [ROOT / "data" / "experiments" / name for name in DEFAULT_INPUT_NAMES]:
            print(f"  - {candidate}", file=sys.stderr)
        print("Pass --input PATH to select a sample manually.", file=sys.stderr)
        return 2

    if args.max_pages < 1:
        print("--max-pages must be a positive integer.", file=sys.stderr)
        return 2

    payload_dir = args.payload_dir
    if not payload_dir.is_absolute():
        payload_dir = (ROOT / payload_dir).resolve()

    if payload_dir.exists() and not args.reuse:
        shutil.rmtree(payload_dir)
    payload_dir.mkdir(parents=True, exist_ok=True)

    from mga.runtime_bridge.external import run_export_artifact

    print(f"Input: {input_path.resolve()}")
    print(f"Payload: {payload_dir.resolve()}")
    print(f"Running export-artifact with max_pages={args.max_pages}, ocr_model={args.ocr_model}...")

    export_result = run_export_artifact(
        input_dir=input_path,
        payload_dir=payload_dir,
        max_pages=args.max_pages,
        ocr_model=args.ocr_model,
    )
    metrics = collect_metrics(payload_dir, export_result)

    metrics_path = payload_dir / "validation-metrics.json"
    metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("Validation metrics:")
    print(json.dumps(metrics, ensure_ascii=False, indent=2, sort_keys=True))
    print(f"Metrics written to: {metrics_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
