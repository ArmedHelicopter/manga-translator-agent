# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Manga Translate Agent (`mga`) — an external-first manga translation agent with character consistency, cultural adaptation, QA proofreading, and memory/wiki system. Uses `manga-image-translator` as the rendering runtime (invoked via subprocess), while `mga` handles intelligence, orchestration, and review.

## Architecture (4 Layers — Token-Optimized, High Cohesion)

```
Layer 0: Core (mga/core) — Zero-dependency foundation
  models.py       — Domain models (PipelineContext, TranslationCandidate, etc.)
  services.py     — TranslationService (unified LLM interface)
  provider_factory.py — create_provider(), ProviderCascade (all 9 providers)
  memory_service.py   — MemoryService (character/scene/terminology)
  cultural_service.py — CulturalService (adaptation, terminology)
  NOTE: All Layer 1+ modules import ONLY from mga.core, never directly from Layer 1 modules

Layer 1: Infrastructure (depends on Layer 0)
  mga/config/          — TOML config loading, provider route resolution
  mga/format/          — FormatAdapter ABC + 6 adapters

Layer 2: Domain (depends on Layer 0)
  mga/memory/          — State management, wiki sync, graph operations
  mga/cultural/        — Extended cultural features (honorific, coinage, etc.)
  mga/qa/              — 9 proofreaders + orchestrator
  mga/learning/        — 4-stage translation learning engine
  mga/distill/         — Knowledge distillation (Character Card, Lorebook, Hermes Skill)
  mga/ocr/             — Blank page detection + recovery + engine bindings (Tesseract, MOCR)

Layer 3: Orchestration (depends on Layers 0-2)
  mga/pipeline/        — 7-stage pipeline + incremental + batch

Layer 4: Interface
  mga/cli/             — Click CLI (translate, benchmark, memory, profile, term)

Layer 5: Runtime Bridge
  mga/runtime_bridge/  — External runtime subprocess integration
  mga/artifacts/       — ArtifactStore, run summary
  mga/benchmark/       — Extraction, translation, external benchmarks
```

## Core Layer Quick Reference

```python
from mga.core import (
    # Models
    PipelineContext, ProjectConfig, TranslationCandidate,
    # Services
    TranslationService, MemoryService, CulturalService,
    # Providers
    create_provider, ProviderCascade,
    # Convenience
    translate_bubble, init_memory,
)

# Create a provider
provider = create_provider("openai", {"api_key": "sk-..."})

# Create services
mem_service = MemoryService("./project")
cult_service = CulturalService("./project")

# Translate a bubble
result = translate_bubble(config, "こんにちは")
```

## Providers (14 concrete)

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
| Cohere | `cohere_provider.py` | Yes | JSON mode | Command A+ models |
| Groq | `groq_provider.py` | No | JSON mode | Fast inference, text-only |
| Mistral | `mistral_provider.py` | Yes | JSON mode | Pixtral vision models |
| Mimo | `mimo_provider.py` | Yes | JSON mode | Chinese provider, domain methods |
| GenericOpenAI | `generic_provider.py` | Auto | JSON mode | Any OpenAI-compatible endpoint |

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

- **Translation modes**: serial (default), `semantic-parallel` (Phase 1), `batch-parallel` (Phase 2)
- **Page footnotes**: `PageFootnoteService` compiles katakana/cultural/coined/sfx footnotes per page
- **OCR guard**: `BlankPageDetector` + `RecoveryOrchestrator` with 5 recovery strategies
- **Incremental** (`incremental.py`) — Load previous chapter context, translate, update profiles
- **Batch** (`batch.py`) — Multi-chapter parallel processing with resume

Orchestrator: `mga/pipeline/orchestrator.py` — `PipelineOrchestrator.run(input_path, output_path, config)`.

## CLI Commands

```bash
# Translate (default: external-core runtime)
manga-translate translate input/ -o output/

# Hot start: learn from existing translations
manga-translate translate ch11/ --learn-from ch01_to_10_translated/ -o output/

# Learn only (no translation)
manga-translate translate existing_translations/ --learn-only --output-profiles profiles/

# Bilingual output
manga-translate translate input.pdf --bilingual -o bilingual.pdf

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

# Run all tests (counts drift — see docs/STATUS.md for the dated snapshot; do not trust hardcoded numbers)
pytest tests/ -q

# Run a single test
pytest tests/qa/test_orchestrator.py -k test_name
```

Python: `>=3.10, <3.13`. Pydantic v2.

## Test Directories

- `tests/` — Host-layer tests: all mga modules (artifacts, benchmark, runtime, QA, cultural, learning, pipeline, format, memory, providers)
- `test/` — Legacy upstream tests. `test_translation.py` and `test_translation_manual.py` require `deepl` module (not installed).

## Key Patterns

**Config split**: Runtime uses OmegaConf in `manga_translator/config.py`. Host layer uses TOML in `mga/config/loader.py` with env var override via `MANGA_TRANSLATE_CONFIG`.

**Artifact contract**: `output/manifest.json`, `external-baseline-summary.json`, `external-baseline-text.txt`, `external-baseline-text-normalized.json`, `run.json`; two-pass render payloads use `.mga-payload/pages.json` plus per-page `artifact-NNNN.json`, `inpainted-NNNN.png`, and `translations-NNNN.json`.

**Monkeypatching**: `manga_translate/cli.py` uses lazy function wrappers so tests can monkeypatch at `manga_translate.cli.*` paths. The actual implementations live in `mga.*` modules.

**Exception hierarchy**: `MangaTranslateError` → `ConfigError`, `ProviderError`, `StageExecutionError`, etc.

**PipelineContext memory shape**: `context.memory_context = {"character_profiles": {speaker: profile}, "page_profiles": {page_id: {speaker: profile}}}`.

**Runtime editability**: The runtime mga invokes is the **worktree-local `manga_translator/`** (`run_export_artifact`/`run_render_only` run `python -m manga_translator` with `cwd=project_root`). It is directly editable — modifying the local runtime is **allowed** when a real runtime bug blocks delivery (PRD §1.2.2; `docs/render_purity_contract.md`). Prefer mga-side fixes; otherwise patch `manga_translator/`.

**End-to-end testing**: See `docs/e2e-testing.md`. E2E = full pipeline run on `data/input/e2e-3pages/` for quick smoke and `data/input/test-pdf-10pages/` for page-to-payload alignment regressions. Invoke through `manga-translate translate ...`. Results MUST be evaluated by a **vision-capable model looking directly at the rendered PNGs** — never by pixel diff or unit tests alone (the **proxy problem**: a green suite while the images are broken). Runtime edits and e2e re-runs go through the local `manga_translator/`.

**Code comments — explain why, not what**: When a change encodes a non-obvious decision or fixes a real bug, the comment must state both (1) **why** it is written this way (the constraint or root-cause decision) and (2) **what breaks** if done the naive way (the failure mode that was hit, or would be). This is defensive: without the trap written down, future agents and humans re-derive the same wrong "obvious" solution and the bug returns. Do not comment mechanics (`# increment i`); comment landmines. Tie non-obvious code to the doc/handoff that records the failure it prevents. Example: the cold-start creation branch in `mga/pipeline/speaker_attribution_stage.py` says *why* it creates a character on a non-generic hint with no match — because without it a fresh work never assigns any `speaker_id` and memory stays empty for the entire run (`docs/handoff-2026-06-22-memory-reassessment.md`).

**Resources on disk — check before asking**: Before claiming a model weight, dependency, or file "needs to be downloaded" or asking the user whether to fetch it, check the local disk first. Runtime models live under `models/` (a symlink to the repo root models dir — e.g. `models/inpainting/lama_large_512px.ckpt` for LaMa inpainting, `models/detection/*.ckpt`, `models/ocr/*.ckpt`). `manga_translator/config.py` `InpainterConfig` defaults already point at these. Don't assert a download is needed when the file is sitting on disk — verify with `ls`/`find` on the `models/` tree first. This applies to any external resource: config defaults, installed packages, cached weights, and symlinked dirs should all be inspected before proposing a fetch.

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
