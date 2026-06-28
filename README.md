# Manga Translate Agent

`mga` is an external-first manga translation agent: it uses `manga-image-translator` as the rendering runtime and adds orchestration, OCR-first artifacts, Vision enrichment, translation QA, and memory/wiki infrastructure on top.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ Layer 0: Models (zero deps)                                                │
│   models/ — Pydantic v2 data models                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ Layer 1: Infrastructure (depends on Layer 0)                                │
│   config/ — TOML config loading, provider route resolution                 │
│   format/ — FormatAdapter ABC + concrete adapters                          │
│   providers/ — LLMProvider ABC + registry/factory/cascade                  │
├─────────────────────────────────────────────────────────────────────────────┤
│ Layer 2: Intelligence (depends on Layers 0-1)                                │
│   memory/ — Dual-structure state (JSON) + wiki projection (Markdown)       │
│   cultural/ — Problem classification, 7 strategies, terminology, honorific │
│   qa/ — 9 proofreaders + orchestrator                                      │
│   learning/ — 4-stage translation learning engine (L1-L4)                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ Layer 3: Orchestration (depends on Layers 0-2)                             │
│   pipeline/ — 7-stage pipeline + incremental + batch                      │
├─────────────────────────────────────────────────────────────────────────────┤
│ Layer 4: Interface                                                          │
│   cli/ — Click CLI (translate, benchmark-external, legacy, memory, profile) │
│   web/ — Web server for monitoring                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ Layer 5: Runtime Bridge                                                    │
│   runtime_bridge/ — External runtime subprocess integration                 │
│   artifacts/ — ArtifactStore for structured output                        │
│   benchmark/ — Extraction, translation, and external benchmarks           │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Features

- **OCR-first manga path** — Runtime OCR and geometry are authoritative for text and rendering.
- **Vision Enrichment** — Vision adds box type, visual footnotes, provisional speaker labels, and voice hints; it does not replace OCR text or final speaker attribution.
- **Translation Context** — Translation prompts consume Vision hints and any available memory/cultural context.
- **QA Proofreading** — 9 proofreader modules: fact, hallucination, character consistency, fictional script, dialog hierarchy, cultural QA, emotion, language evolution, style polish.
- **Memory/Wiki Infrastructure** — Dual-structure: JSON canonical state + Markdown wiki projection. Includes character graph, evolution tracking, profile loading/building.
- **Cultural Adaptation** — 7 strategies: literal, adapt, coined, transliterate, contextual, preserve, hybrid. Includes terminology DB, honorific compensator, coinage detector.
- **Learning Engine** — 4-stage pipeline: L1 Align → L2 Dual Vision → L3 Pattern Extractor → L4 Validator.
- **Incremental/Batch Processing** — Load previous chapter context, translate, update profiles. Multi-chapter parallel processing with resume.
- **LLM Providers** — Stage-aware provider registry/factory with cascade fallback; see `docs/STATUS.md` for dated counts.
- **Format Adapters** — Images, PDF, EPUB, CBZ/CBR, MOBI, Bilingual PDF, and additional adapters; see `docs/STATUS.md` for dated counts.
- **Vision Capability Pre-check** — Opt-in auto-switch when configured provider lacks vision support.

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Translate (cold start)
manga-translate translate input/ -o output/

# Hot start: learn from existing translations
manga-translate translate ch11/ --learn-from ch01_to_10_translated/ -o output/

# Bilingual output
manga-translate translate input.pdf --bilingual -o bilingual.pdf

# Run tests
pytest tests/ -v
```

## Package Layout

```
mga/
├── artifacts/       # ArtifactStore for structured output
├── benchmark/       # External runtime benchmarks
├── cache/           # LLM response caching
├── cli/             # Click CLI (translate, benchmark, legacy, memory, profile, term)
├── config/          # TOML config loading, provider route resolution
├── cultural/        # Problem classification, strategies, terminology, honorific, coinage
├── format/          # FormatAdapter registry (images, PDF, EPUB, CBZ/CBR, MOBI, bilingual, ...)
├── learning/        # 4-stage translation learning engine (L1-L4)
├── memory/          # Dual-structure state + wiki + graph + profiles + evolution tracker
├── models/          # Pydantic v2 data models
├── ocr/             # OCR guard, recovery strategies, detector
├── pipeline/        # Manga/novel pipeline stages + incremental + batch
├── providers/       # LLMProvider ABC + concrete providers + factory + cascade
├── qa/              # 9 proofreaders + orchestrator
├── review/          # Review diff tools
├── runtime_bridge/  # External runtime subprocess integration
├── util/            # Utility functions (JSON helpers)
└── web/             # Web server for monitoring
```

## Pipeline

```
Format → OCR Artifact → Vision Enrichment → Speaker Attribution → Character → Translation → QA → Render → Output
```

### Two-Pass Architecture

When the external runtime (`manga-image-translator`) is available:

1. **Pass 1** — Runtime runs detect/OCR/merge/inpaint per source page, exports `artifact-NNNN.json` + `inpainted-NNNN.png`, and records `pages.json` so output page `N` mounts payload `N`.
2. **Enrichment + Intelligence** — mga reads OCR text regions, runs Vision enrichment for box types, visual footnotes, and provisional voice hints, then runs character/cultural adaptation, translation, and QA
3. **Pass 2** — Runtime loads mga per-page `translations-NNNN.json` and renders them onto the matching inpainted image

### OCR/Runtime Authority

OCR/runtime output is authoritative for bubble text and render geometry. Vision enrichment must not overwrite OCR text or drive final speaker attribution; OCR-missed author-drawn text is carried as page-level footnotes.

### Memory Loop

The intelligent layer has a minimum page-sequential memory loop for formal `speaker_id`: translated bubbles update `CharacterState`, later pages can read the updated style context, and `context.artifacts["character_memory"]` records the trace.

## Provider Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ ProviderFactory (factory.py)                               │
│   create_provider(name, settings) → LLMProvider            │
│   register_provider(name, cls)                             │
│   get_provider(name, **kwargs) → LLMProvider (compat)     │
├─────────────────────────────────────────────────────────────┤
│ ProviderRegistry (registry.py)                             │
│   Stage-aware routing: primary → fallback → local          │
│   ProviderCascade for automatic failover                    │
└─────────────────────────────────────────────────────────────┘
```

Supported providers: `openai`, `anthropic`, `gemini`, `deepseek`, `openrouter`, `ollama`, `vllm`, `lmstudio`, `llamacpp`

## CLI Reference

| Command | Description |
|---------|-------------|
| `manga-translate translate input/ -o output/` | Translate manga |
| `manga-translate translate input/ --learn-from dir/ -o output/` | Warm start from existing translations |
| `manga-translate translate input/ --bilingual -o output/` | Output bilingual PDF |
| `manga-translate translate input/ --save-json -o output/` | Save translation report + debug artifacts |
| `manga-translate translate input/ --artifact-payload-dir dir/ -o output/` | Reuse exported runtime payload |
| `manga-translate benchmark-external` | Run external runtime benchmark |
| `manga-translate legacy benchmark-extraction` | Legacy extraction benchmark |
| `manga-translate memory init/sync` | Memory management |
| `manga-translate profile list` | List character profiles |
| `manga-translate term list` | List terminology |

## Configuration

Create `config.toml` or use `~/.config/manga-translate/config.toml`:

```toml
[providers]
openai.api_key = "sk-..."
anthropic.api_key = "sk-ant-..."

[[provider_routes.vision]]
primary = { provider = "openai", model = "gpt-4o" }
fallback = { provider = "anthropic", model = "claude-3-5-sonnet" }

[[provider_routes.translate]]
primary = { provider = "openai", model = "gpt-4o" }
fallback = { provider = "deepseek", model = "deepseek-chat" }
```

## Tests

```bash
pytest tests/ -v                    # All tests
pytest tests/providers/ -v         # Provider tests
pytest tests/qa/ -v                # QA proofreaders
pytest tests/cultural/ -v          # Cultural adaptation
pytest tests/learning/ -v          # Learning engine
pytest tests/memory/ -v           # Memory/wiki/graph
pytest tests/pipeline/ -v          # Pipeline stages + incremental + batch
pytest tests/ocr/ -v               # OCR guard and recovery
```

## Related Docs

- [docs/SPEC.md](docs/SPEC.md) — Full system specification
- [docs/PRD.md](docs/PRD.md) — Product requirements
- [docs/ROADMAP.md](docs/ROADMAP.md) — Module delivery roadmap
- [CLAUDE.md](CLAUDE.md) — Developer guidance for Claude Code