# Manga Translate Agent

`mga` is an external-first manga translation agent: it uses `manga-image-translator` as the rendering runtime and adds orchestration, OCR-first artifacts, Vision enrichment, translation QA, and memory/wiki infrastructure on top.

## Architecture

```text
┌──────────────────────────────────────────────┐
│ mga intelligence layer                       │
│ OCR-aware translation · Vision enrichment   │
│ QA · memory/wiki infrastructure             │
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

- **OCR-first manga path** — Runtime OCR and geometry are authoritative for text and rendering.
- **Vision Enrichment** — Vision adds box type, visual footnotes, provisional speaker labels, and voice hints; it does not replace OCR text or final speaker attribution.
- **Translation Context** — Translation prompts consume Vision hints and any available memory/cultural context.
- **QA Proofreading** — Proofreader modules exist for fact, hallucination, character consistency, fictional script, dialog hierarchy, cultural QA, emotion, language evolution, and style polish checks.
- **Memory/Wiki Infrastructure** — Dual-structure JSON state plus Markdown wiki projection.
- **Learning Engine Infrastructure** — L1-L4 learning modules and tests exist, but the manga production path still needs stronger end-to-end validation before treating warm-start character simulation as shipped.
- **Incremental/Batch Infrastructure** — Modules exist for future workflows; current default product path is the two-pass manga CLI.
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

# Run tests
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
Format → OCR Artifact → Vision Enrichment → Character+Culture → Translation → QA → Render → Output
```

When the external runtime (`manga-image-translator`) is available, the pipeline uses a two-pass architecture:

1. **Pass 1** — Runtime runs detect/OCR/merge/inpaint, exports `artifact.json` + `inpainted.png`
2. **Enrichment + Intelligence** — mga reads OCR text regions, runs Vision enrichment for box types, visual footnotes, and provisional voice hints, then runs character/cultural adaptation, translation, and QA
3. **Pass 2** — Runtime loads mga translations and renders them onto the inpainted image

OCR/runtime output is authoritative for bubble text and render geometry. Vision enrichment must not overwrite OCR text or drive final speaker attribution; OCR-missed author-drawn text is carried as page-level footnotes. When the runtime is unavailable, the pipeline falls back to LLM vision for degraded JSON artifacts only (no guaranteed rendered images).

Current implementation status:

- The installed `manga-translate` entrypoint resolves to `mga.cli.main:main` and enters the mga pipeline after runtime artifact export.
- The compatibility shim `manga_translate.cli` is legacy external-core plumbing kept for older tests/imports; it is not the source of truth for the product pipeline.
- The intelligent layer now has a minimum page-sequential memory loop for formal `speaker_id`: translated bubbles update `CharacterState`, later pages can read the updated style context, and `context.artifacts["character_memory"]` records the trace. The current style model is still a lightweight heuristic, not a mature character voice model.
- Vision provisional speakers are prompt hints only. `SpeakerAttributionStage` may conservatively promote exact matches against existing character profiles into formal `speaker_id`; unmatched or generic hints are traced but not written to character memory.
- Provider routing is stage-aware in config, but automatic primary → fallback → local cascade is not yet fully implemented across every stage.

## CLI Reference

| Command | Description |
|---------|-------------|
| `manga-translate input/ -o output/` | Translate manga |
| `manga-translate input/ --learn-from dir/` | Warm start from existing translations |
| `manga-translate --bilingual` | Output bilingual PDF |
| `manga-translate --save-json` | Save translation report + debug artifacts |
| `manga-translate --artifact-payload-dir dir/` | Reuse an exported runtime payload and run the mga pipeline |
| `manga-translate benchmark-external` | Run external runtime benchmark |
| `manga-translate legacy benchmark-extraction` | Legacy extraction benchmark |
| `manga-translate memory init/sync` | Memory management |
| `manga-translate profile list` | List character profiles |
| `manga-translate term list` | List terminology |

## Tests

```bash
pytest tests/ -v
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
