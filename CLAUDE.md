# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Manga Translate Agent (`mga`) — an external-first manga translation agent with character consistency, cultural adaptation, QA proofreading, and memory/wiki system. Uses `manga-image-translator` as the rendering runtime (invoked via subprocess), while `mga` handles intelligence, orchestration, and review.

## Architecture (6 Layers)

```
Layer 0: Models (zero deps)
  mga/models/          — Pydantic v2 data models

Layer 1: Infrastructure (depends on Layer 0)
  mga/config/          — TOML config loading, provider route resolution
  mga/format/          — FormatAdapter ABC + 6 adapters (images, PDF, EPUB, CBZ/CBR, MOBI, bilingual)
  mga/providers/       — LLMProvider ABC + 9 providers + registry with fallback cascade

Layer 2: Intelligence (depends on Layers 0-1)
  mga/memory/          — Dual-structure state (JSON) + wiki projection (Markdown) + graph + profiles
  mga/cultural/        — Problem classification, 7 strategies, terminology DB, honorific compensation, coinage detection
  mga/qa/              — 9 proofreaders + orchestrator
  mga/learning/        — 4-stage translation learning engine (L1-L4)

Layer 3: Orchestration (depends on Layers 0-2)
  mga/pipeline/        — 7-stage pipeline + incremental translation + batch processing

Layer 4: Interface
  mga/cli/             — Click CLI (translate, benchmark-external, legacy, memory, profile, term)

Layer 5: Runtime Bridge
  mga/runtime_bridge/  — External runtime subprocess integration
  mga/artifacts/       — ArtifactStore for structured output
  mga/benchmark/       — Extraction, translation, and external benchmarks
```

## Providers (9 concrete)

| Provider | File | Vision | Structured | Notes |
|----------|------|--------|------------|-------|
| OpenAI | `openai_provider.py` | Yes | JSON mode | Default primary |
| Anthropic | `anthropic_provider.py` | Yes | Prompt-based | Claude models |
| Gemini | `gemini_provider.py` | Yes | JSON mode | Google models |
| DeepSeek | `deepseek_provider.py` | No | JSON mode | Text-only, cheap |
| OpenRouter | `openrouter_provider.py` | Yes* | JSON mode | Unified gateway |
| Ollama | `ollama_provider.py` | Yes | Prompt-based | Local, REST API |
| vLLM | `vllm_provider.py` | Yes | JSON mode | OpenAI-compatible local |
| LM Studio | `lmstudio_provider.py` | Yes | JSON mode | Local, OpenAI-compatible |
| llama.cpp | `llamacpp_provider.py` | No | JSON mode | Text-only, llama-server |

Registry: `mga/providers/registry.py` — `get_provider(name)`, `select_provider(stage, config)` with primary → fallback → local cascade.

## Format Adapters (6 concrete)

| Format | File | Input | Output |
|--------|------|-------|--------|
| Images | `images.py` | Directory of images | Copy to output dir |
| PDF | `pdf_adapter.py` | PyMuPDF page rendering | New PDF from images |
| EPUB | `epub_adapter.py` | ZIP extraction | Replace images in EPUB |
| CBZ/CBR | `cbz_adapter.py` | ZIP/RAR extraction | CBZ output |
| MOBI | `mobi_adapter.py` | Calibre ebook-convert → EPUB | CBZ output |
| Bilingual | `bilingual.py` | Side-by-side original/translation | Bilingual PDF output |

Factory: `mga/format/__init__.py` — `get_adapter(format_name)`.

## QA Layer (9 proofreaders)

| Proofreader | Priority | Focus |
|-------------|----------|-------|
| FactCheck | 10 | Numeric/name consistency, omission detection |
| HallucinationGuard | 15 | Name fidelity, number fidelity, term consistency |
| CharacterConsistency | 20 | Voice patterns, catchphrases, tone drift |
| FictionalScript | 25 | Symbol preservation, mixed-script detection |
| DialogHierarchy | 30 | Honorific levels, form-of-address |
| CulturalQA | 35 | Terminology consistency, coined term preservation |
| EmotionConsistency | 40 | Scene mood vs emotion matching |
| LanguageEvolution | 50 | Post-evolution pattern detection |
| StylePolish | 60 | Punctuation, formatting, readability |

Orchestrator: `mga/qa/orchestrator.py` — `QAOrchestrator.proofread(page, translations, context)`.

## Memory/Wiki System

Dual-structure per ADR:
- `memory/state/` — JSON canonical source (CharacterState, SceneState, TermState, DecisionState, MemoryIndex)
- `memory/*` — Markdown wiki projection (human-readable)

Key modules:
- `StateManager` — CRUD for state entities
- `WikiProjection` — Markdown generation from state
- `MemoryRetrieval` — Context retrieval for translation (character profiles, scene context, terminology)
- `CharacterGraph` — NetworkX relationship graph with formality levels
- `GraphRetrieval` — Relationship-aware context for translation
- `EvolutionTracker` — Voice change detection and changelog
- `ProfileLoader` — Load character profiles for prompt injection
- `ProfileBuilder` — Build/update profiles from translations

## Cultural Adaptation Layer

- **Problem Classifier** (`classifier.py`) — 7 cultural problem types
- **Strategies** (`strategies.py`) — 7 SPEC-aligned strategies: literal, adapt, coined, transliterate, contextual, preserve, hybrid
- **Terminology DB** (`terminology_db.py`) — Per-work term storage
- **Honorific Compensator** (`honorific.py`) — 5-level honorific handling
- **Coinage Detector** (`coinage_detector.py`) — Auto-discover coined terms (detect → propose → confirm → register)
- **Term Classifier** (`term_classifier.py`) — 7-level grading (G1 universal → G7 fictional)

## Learning Engine

4-stage pipeline for extracting translation patterns from existing translations:
- **L1 Align** (`aligner.py`) — File-name matching + visual verification
- **L2 Dual Vision** (`dual_vision.py`) — LLM-based dual page understanding
- **L3 Pattern Extractor** (`pattern_extractor.py`) — Character language, terms, style, relationships
- **L4 Validator** (`validator.py`) — Consistency and completeness checks

Engine: `mga/learning/engine.py` — `LearningEngine.learn(learn_dir)`.

## Pipeline (7 stages + incremental + batch)

```
Format → Vision → Character+Culture → Translation → QA → Render → Output
```

- **Incremental** (`incremental.py`) — Load previous chapter context, translate, update profiles
- **Batch** (`batch.py`) — Multi-chapter parallel processing with resume

Orchestrator: `mga/pipeline/orchestrator.py` — `PipelineOrchestrator.run(input_path, output_path, config)`.

## CLI Commands

```bash
# Translate (default: external-core runtime)
manga-translate input/ -o output/

# Hot start: learn from existing translations
manga-translate ch11/ --learn-from ch01_to_10_translated/ -o output/

# Learn only (no translation)
manga-translate --learn-only existing_translations/ --output-profiles profiles/

# Bilingual output
manga-translate input.pdf --bilingual -o bilingual.pdf

# External benchmark
manga-translate benchmark-external input/ -o output/

# Legacy research
manga-translate legacy benchmark-extraction input/ -o output/

# Memory management
manga-translate memory init project_dir/
manga-translate memory sync project_dir/

# Profile/term management
manga-translate profile list project_dir/
manga-translate term list project_dir/
```

## Build & Test Commands

```bash
# Install (editable)
pip install -e ".[dev]"

# Run all tests (329 tests)
pytest tests/ -v

# Run a single test
pytest tests/qa/test_orchestrator.py -k test_name
```

Python: `>=3.10, <3.13`. Pydantic v2.

## Test Directories

- `tests/` — Host-layer tests: all mga modules (artifacts, benchmark, runtime, QA, cultural, learning, pipeline, format, memory, providers)
- `test/` — Legacy upstream tests. `test_translation.py` and `test_translation_manual.py` require `deepl` module (not installed).

## Key Patterns

**Config split**: Runtime uses OmegaConf in `manga_translator/config.py`. Host layer uses TOML in `mga/config/loader.py` with env var override via `MANGA_TRANSLATE_CONFIG`.

**Artifact contract**: `output/manifest.json`, `external-baseline-summary.json`, `external-baseline-text.txt`, `external-baseline-text-normalized.json`, `run.json`.

**Monkeypatching**: `manga_translate/cli.py` uses lazy function wrappers so tests can monkeypatch at `manga_translate.cli.*` paths. The actual implementations live in `mga.*` modules.

**Exception hierarchy**: `MangaTranslateError` → `ConfigError`, `ProviderError`, `StageExecutionError`, etc.

**PipelineContext memory shape**: `context.memory_context = {"character_profiles": {speaker: profile}, "page_profiles": {page_id: {speaker: profile}}}`.
