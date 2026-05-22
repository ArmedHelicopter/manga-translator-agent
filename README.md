# Manga Translate Agent

`mga` is an external-first manga translation agent: it uses `manga-image-translator` as the rendering runtime and adds intelligence, orchestration, cultural adaptation, character consistency, QA proofreading, and memory/wiki on top.

## Architecture

```text
┌──────────────────────────────────────────────┐
│ mga intelligence layer                       │
│ character consistency · QA · memory/wiki    │
│ cultural adaptation · learning engine        │
├──────────────────────────────────────────────┤
│ mga orchestration layer                      │
│ 7-stage pipeline · artifacts · benchmark     │
│ incremental · batch · review · config       │
├──────────────────────────────────────────────┤
│ external runtime core                        │
│ detection · OCR · inpainting · rendering    │
│ provided by manga-image-translator          │
└──────────────────────────────────────────────┘
```

## Features

- **Character Consistency** — Character profiles injected into translation prompts; same character speaks differently to different people
- **Relationship Graph** — NetworkX graph with formality levels (intimate/casual/polite/formal/honorific); honorific-aware translation
- **Cultural Adaptation** — 7 translation strategies, 7-level term grading, coinage auto-discovery, honorific compensation
- **QA Proofreading** — 9 proofreaders: fact check, hallucination guard, character consistency, fictional script, dialog hierarchy, cultural QA, emotion consistency, language evolution, style polish
- **Learning Engine** — Extract character profiles, terminology, and style guides from existing translations (warm start)
- **Memory/Wiki** — Dual-structure: JSON state (canonical) + Markdown wiki (human-readable)
- **Incremental Translation** — Load previous chapter context, translate new chapters, update profiles
- **Batch Processing** — Multi-chapter parallel processing with resume
- **9 LLM Providers** — OpenAI, Anthropic, Gemini, DeepSeek, OpenRouter, Ollama, vLLM, LM Studio, llama.cpp
- **6 Format Adapters** — Images, PDF, EPUB, CBZ/CBR, MOBI, Bilingual PDF

## Quick Start

```bash
# Install
pip install -e ".[dev]"

# Translate (cold start)
manga-translate input/ -o output/

# Hot start: learn from existing translations
manga-translate ch11/ --learn-from ch01_to_10_translated/ -o output/

# Bilingual output
manga-translate input.pdf --bilingual -o bilingual.pdf

# Run tests (329 tests)
pytest tests/ -v
```

## Package Layout

```text
mga/
├── artifacts/       # ArtifactStore for structured output
├── benchmark/       # Extraction, translation, and external benchmarks
├── cli/             # Click CLI (translate, benchmark-external, legacy, memory, profile, term)
├── config/          # TOML config loading, provider route resolution
├── cultural/        # Problem classification, strategies, terminology DB, honorific, coinage
├── format/          # FormatAdapter ABC + 6 adapters
├── learning/        # 4-stage translation learning engine (L1-L4)
├── memory/          # Dual-structure state + wiki + graph + profiles + evolution tracker
├── models/          # Pydantic v2 data models
├── pipeline/        # 7-stage pipeline + incremental + batch
├── providers/       # LLMProvider ABC + 9 providers + registry
├── qa/              # 9 proofreaders + orchestrator
├── review/          # Review diff tools
└── runtime_bridge/  # External runtime subprocess integration
```

## Pipeline

```
Format → Vision → Character+Culture → Translation → QA → Render → Output
```

When the external runtime (`manga-image-translator`) is available, the pipeline uses a two-pass architecture:

1. **Pass 1** — Runtime runs detect/OCR/merge/inpaint, exports `artifact.json` + `inpainted.png`
2. **Intelligence** — mga reads the artifact, runs character attribution, cultural adaptation, translation, and QA
3. **Pass 2** — Runtime loads mga translations and renders them onto the inpainted image

When the runtime is unavailable, the pipeline falls back to LLM vision for OCR and produces JSON artifacts only (no rendered images).

Each stage can independently select its LLM provider with primary → fallback → local cascade.

## CLI Reference

| Command | Description |
|---------|-------------|
| `manga-translate input/ -o output/` | Translate manga |
| `manga-translate --learn-from dir/` | Warm start from existing translations |
| `manga-translate --learn-only dir/` | Learn profiles without translating |
| `manga-translate --bilingual` | Output bilingual PDF |
| `manga-translate --save-json` | Save translation report + debug artifacts |
| `manga-translate benchmark-external` | Run external runtime benchmark |
| `manga-translate legacy benchmark-extraction` | Legacy extraction benchmark |
| `manga-translate memory init/sync` | Memory management |
| `manga-translate profile list` | List character profiles |
| `manga-translate term list` | List terminology |

## Tests

```bash
pytest tests/ -v          # All 329 tests
pytest tests/qa/ -v       # QA proofreaders
pytest tests/cultural/    # Cultural adaptation
pytest tests/learning/    # Learning engine
pytest tests/memory/      # Memory/wiki/graph
pytest tests/pipeline/    # Pipeline stages + incremental + batch
```

## Related Docs

- [docs/SPEC.md](docs/SPEC.md) — Full system specification
- [docs/PRD.md](docs/PRD.md) — Product requirements
- [docs/ROADMAP.md](docs/ROADMAP.md) — Module delivery roadmap
- [CLAUDE.md](CLAUDE.md) — Developer guidance for Claude Code
