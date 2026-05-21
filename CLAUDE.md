# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Manga Translate Agent (`mga`) — an external-first manga translation agent with character consistency, cultural adaptation, QA proofreading, and memory/wiki system. Uses `manga-image-translator` as the rendering runtime (invoked via subprocess), while `mga` handles intelligence, orchestration, and review.

## Architecture (7 Layers)

```
Layer 0: Models (zero deps)
  mga/models/          — Pydantic v2 data models

Layer 1: Infrastructure (depends on Layer 0)
  mga/config/          — TOML config loading, provider route resolution
  mga/format/          — FormatAdapter ABC + 5 adapters (images, PDF, EPUB, CBZ, MOBI)
  mga/providers/       — LLMProvider ABC + 6 providers + registry with fallback cascade

Layer 2: Intelligence (depends on Layers 0-1)
  mga/memory/          — Dual-structure state (JSON) + wiki projection (Markdown)
  mga/cultural/        — Problem classification, strategies, terminology DB, honorific compensation
  mga/qa/              — 6 proofreaders + orchestrator

Layer 3: Orchestration (depends on Layers 0-2)
  mga/pipeline/        — 7-stage pipeline orchestrator

Layer 4: Interface
  mga/cli/             — Click CLI (translate, benchmark-external, legacy)
  manga_translate/     — Compatibility shim for backward-compatible test imports

Layer 5: Runtime Bridge
  mga/runtime_bridge/  — External runtime subprocess integration
  mga/artifacts/       — ArtifactStore for structured output
  mga/benchmark/       — Extraction, translation, and external benchmarks
```

## Providers (6 concrete)

| Provider | File | Vision | Structured | Notes |
|----------|------|--------|------------|-------|
| OpenAI | `openai_provider.py` | Yes | JSON mode | Default primary |
| Anthropic | `anthropic_provider.py` | Yes | Prompt-based | Claude models |
| Gemini | `gemini_provider.py` | Yes | JSON mode | Google models |
| DeepSeek | `deepseek_provider.py` | No | JSON mode | Text-only, cheap |
| Ollama | `ollama_provider.py` | Yes | Prompt-based | Local, REST API |
| vLLM | `vllm_provider.py` | Yes | JSON mode | OpenAI-compatible local |

Registry: `mga/providers/registry.py` — `get_provider(name)`, `select_provider(stage, config)` with primary → fallback → local cascade.

## Format Adapters (5 concrete)

| Format | File | Input | Output |
|--------|------|-------|--------|
| Images | `images.py` | Directory of images | Copy to output dir |
| PDF | `pdf_adapter.py` | PyMuPDF page rendering | New PDF from images |
| EPUB | `epub_adapter.py` | ZIP extraction | Replace images in EPUB |
| CBZ/CBR | `cbz_adapter.py` | ZIP/RAR extraction | CBZ output |
| MOBI | `mobi_adapter.py` | Calibre ebook-convert → EPUB | CBZ output |

Factory: `mga/format/__init__.py` — `get_adapter(format_name)`.

## QA Layer (6 proofreaders)

| Proofreader | Priority | Focus |
|-------------|----------|-------|
| FactCheck | 10 | Numeric/name consistency, omission detection |
| CharacterConsistency | 20 | Voice patterns, catchphrases, tone drift |
| DialogHierarchy | 30 | Honorific levels, form-of-address |
| EmotionConsistency | 40 | Scene mood vs emotion matching |
| LanguageEvolution | 50 | Post-evolution pattern detection |
| StylePolish | 60 | Punctuation, formatting, readability |

Orchestrator: `mga/qa/orchestrator.py` — `QAOrchestrator.proofread(page, translations, context)`.

## Memory/Wiki System

Dual-structure per ADR:
- `memory/state/` — JSON canonical source (CharacterState, SceneState, TermState, DecisionState)
- `memory/*` — Markdown wiki projection (human-readable)

Modules: `StateManager`, `WikiProjection`, `MemoryRetrieval`, `state_to_wiki()`, `wiki_to_state()`.

## Pipeline (7 stages)

```
Format → Vision → Character+Culture → Translation → QA → Render → Output
```

Orchestrator: `mga/pipeline/orchestrator.py` — `PipelineOrchestrator.run(input_path, output_path, config)`.

## Build & Test Commands

```bash
# Install (editable)
pip install -e ".[dev]"

# Run all tests (both legacy and host-layer)
pytest tests/ test/ --ignore=test/test_translation.py --ignore=test/test_translation_manual.py

# Run only host-layer tests
pytest tests/

# Run only legacy/runtime tests
pytest test/ --ignore=test/test_translation.py --ignore=test/test_translation_manual.py

# Run a single test
pytest tests/benchmark/test_benchmark.py -k test_name
```

Python: `>=3.10, <3.13`. Pydantic v2 (pinned at 2.5.0).

## Test Directories

- `test/` — Legacy upstream tests. `test_translation.py` and `test_translation_manual.py` require `deepl` module (not installed).
- `tests/` — Host-layer tests: CLI smoke, benchmark, runtime bridge.

## Key Patterns

**Config split**: Runtime uses OmegaConf in `manga_translator/config.py`. Host layer uses TOML in `mga/config/loader.py` with env var override via `MANGA_TRANSLATE_CONFIG`.

**Artifact contract**: `output/manifest.json`, `external-baseline-summary.json`, `external-baseline-text.txt`, `external-baseline-text-normalized.json`, `run.json`.

**Monkeypatching**: `manga_translate/cli.py` uses lazy function wrappers so tests can monkeypatch at `manga_translate.cli.*` paths. The actual implementations live in `mga.*` modules.

**Exception hierarchy**: `MangaTranslateError` → `ConfigError`, `ProviderError`, `StageExecutionError`, etc.
