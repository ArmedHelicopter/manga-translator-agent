# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Manga Translate Agent (`mga`) is an external-first manga translation host. It wraps `manga-image-translator` (the upstream runtime) with orchestration, artifact normalization, benchmarking, and review workflows. The runtime is invoked via subprocess, not imported.

## Architecture

Three-layer stack:

```
mga intelligence layer     (character consistency, QA, memory/wiki)
mga orchestration layer    (artifacts, benchmark, review, config)
external runtime core      (detection, OCR, inpainting, rendering)
```

- **`manga_translator/`** — Upstream runtime. Self-contained pipeline (detect → OCR → translate → inpaint → render). Entry point: `python -m manga_translator`.
- **`mga/`** — Host layer. Runs the runtime as a subprocess, normalizes outputs into structured artifacts, provides benchmarking and review.

The bridge between them is `mga/runtime_bridge/external.py` — it resolves the runtime repo, builds CLI commands, runs the subprocess, and parses outputs. It sanitizes the environment (strips conda, sets `LD_PRELOAD`) before launch.

## Build & Test Commands

```bash
# Install (editable)
pip install -e ".[dev]"

# Run all tests (both legacy and host-layer)
pytest

# Run only host-layer tests
pytest tests/

# Run only legacy/runtime tests
pytest test/

# Run a specific test file
pytest tests/benchmark/test_benchmark.py

# Run a single test by name
pytest tests/benchmark/test_benchmark.py -k test_name

# Lint (non-blocking in CI)
pylint manga_translator/ mga/

# Docker build
make build-image
```

Python requirement: `>=3.10, <3.13`.

## Test Directories

- `test/` — Legacy upstream tests. Uses conftest.py with custom `--translator`, `--target-lang` flags. Manual translator tests: `pytest test/test_translation_manual.py --translator sugoi --target-lang ENG`
- `tests/` — New host-layer tests. Smoke tests for CLI, benchmark normalization, fixtures.

## Key Design Patterns

**Config is split**: Runtime uses Pydantic models in `manga_translator/config.py` (with OmegaConf). Host layer uses TOML-based provider config in `mga/config/loader.py`.

**Artifact contract**: A translated run produces `output/manifest.json`, `external-baseline-summary.json`, `external-baseline-text.txt`, `external-baseline-text-normalized.json`, and `run.json`. The `ArtifactStore` class in `mga/artifacts/store.py` manages this.

**Pipeline contract**: `manga_translator/pipeline/contract.py` defines `PostOCRArtifact`, `OCRLineSnapshot`, and `RegionOrderEntry` dataclasses — the structured data format between OCR and translation stages.

**Exception hierarchy**: `mga/exceptions.py` defines `MangaTranslateError` base with `ConfigError`, `ProviderError`, `StageExecutionError`, etc.

## Migration Notes

This repo is mid-migration from a monolithic runtime to host+external-core. Many `mga/` subpackages (`cli/`, `memory/`, `qa/`, `review/`) are stubs. The `mga` code sometimes imports from `manga_translate` (singular) — this is a legacy namespace from before the migration.

## CI

GitHub Actions CI (`.github/workflows/ci.yml`) only tests `test/`, not `tests/`. It runs on Python 3.10+3.11, ubuntu-latest. Pylint runs but is non-blocking.
