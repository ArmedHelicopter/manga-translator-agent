<!-- /autoplan restore point: /home/exusiai/.gstack/projects/ArmedHelicopter-manga-translator-agent/mga-layer-bootstrap-autoplan-restore-20260521-232030.md -->
# MGA Branch Completion Plan

## Goal

Ship the `mga-layer-bootstrap` branch as a merge-ready PR to `main`. The intelligence layer (Modules A-F) is fully implemented with 329 passing tests. This plan covers the remaining work to make the branch production-ready.

## Current State (as of 2026-05-22)

Implemented and tested:
- **Layer 0: Models** — Pydantic v2 data models (Page, Translation, Project, Format)
- **Layer 1: Infrastructure** — TOML config, 9 LLM providers with registry/fallback, 6 format adapters
- **Layer 2: Intelligence** — Memory/wiki (state + wiki projection + graph + profiles), cultural adaptation (7 strategies, coinage detection, honorific compensation, term classifier), QA (9 proofreaders + orchestrator), learning engine (4-stage L1-L4)
- **Layer 3: Orchestration** — 7-stage pipeline, incremental translation, batch processing
- **Layer 4: Interface** — Click CLI (translate, benchmark-external, legacy, memory, profile, term)
- **Layer 5: Runtime Bridge** — External runtime subprocess integration, artifact store, two-pass render mode

Test coverage: 329 tests passing across 53 test files in 1.0s.
Console script: `manga-translate` registered and working.

### Phase 1: DONE — Wire Intelligence Pipeline to Renderer

Implemented two-pass architecture:
- `manga_translator/pipeline/contract.py` — serialize/deserialize render payload (artifact.json + inpainted.png + translations.json)
- `manga_translator/args.py` — `--export-artifact` and `--render-only` CLI flags
- `manga_translator/manga_translator.py` — export hook after inpainting + `render_only()` method
- `manga_translator/mode/local.py` — render-only dispatch in MangaTranslatorLocal
- `mga/runtime_bridge/external.py` — `run_export_artifact()` and `run_render_only()` functions
- `mga/pipeline/vision_stage.py` — reads from artifact.json when available (real OCR + geometry)
- `mga/pipeline/render_stage.py` — writes translations.json + calls render-only mode
- `mga/pipeline/orchestrator.py` — accepts metadata dict for passing payload_dir
- `mga/cli/main.py` — translate command orchestrates two-pass flow with graceful fallback
- `pyproject.toml` — `[project.scripts] manga-translate = "mga.cli.main:main"`

## What Remains

### Phase 2: Branch Hygiene

1. **Remove stale docs** — `README.mga-draft.md` is superseded by the current `README.md`. Remove it.
2. **Update ROADMAP** — Mark Modules A-F as complete. Add post-merge roadmap items.
3. **Clean up plan.md** — Remove or convert to post-merge TODO after merge.
4. **Verify no broken imports** — Confirm all tests pass in CI-like isolation.
5. **Update README** — Ensure it accurately describes the end-to-end two-pass flow.

### Phase 3: PR Preparation

1. **Write PR description** — Summary of what the branch adds (6 modules, 329+ tests, two-pass pipeline).
2. **Squash or organize commits** — The branch has 18+ commits. Decide whether to squash into logical groups or keep as-is.
3. **Final test run** — Full `pytest tests/ -v` pass.
4. **Create PR** — Target `main`, include architecture diagram and feature list.

## Architecture (what ships in this PR)

```text
mga/
├── models/          — Pydantic v2 data models (Layer 0)
├── config/          — TOML config + provider route resolution (Layer 1)
├── format/          — FormatAdapter ABC + 6 adapters (Layer 1)
├── providers/       — LLMProvider ABC + 9 providers + registry (Layer 1)
├── memory/          — State + wiki + graph + profiles + evolution (Layer 2)
├── cultural/        — Classifier + 7 strategies + terminology + honorific + coinage (Layer 2)
├── qa/              — 9 proofreaders + orchestrator (Layer 2)
├── learning/        — 4-stage learning engine L1-L4 (Layer 2)
├── pipeline/        — 7-stage pipeline + incremental + batch (Layer 3)
├── cli/             — Click CLI entry points (Layer 4)
├── runtime_bridge/  — External runtime subprocess integration (Layer 5)
├── artifacts/       — Structured output store (Layer 5)
├── benchmark/       — Extraction + translation benchmarks (Layer 5)
├── review/          — Translation review reports (Layer 5)
└── exceptions.py    — Exception hierarchy
```

## Success Criteria

- All 329 tests pass
- `pip install -e ".[dev]"` works cleanly
- `manga-translate --help` shows all commands
- README accurately describes what ships
- No broken imports or missing `__init__.py` files
- PR is reviewable and merge-ready

## Explicit Non-Goals

- Runtime seam refactor (OCR-post interceptor) — deferred to next branch
- Real-world translation quality benchmarks — requires manual evaluation
- Novel mode production polish — functional but not battle-tested
- Full CI/CD pipeline setup — out of scope for this PR

## GSTACK REVIEW REPORT

| Run | Skill | Status | Verdict | Notes |
|---|---|---|---|---|
| 1 | `autoplan` Phase 1 (CEO) | completed | challenge | Both voices found pipeline-renderer disconnect, missing entry point, two CLIs |
| 2 | `autoplan` Phase 2 (Design) | skipped | no UI scope | |
| 3 | `autoplan` Phase 3 (Eng) | completed | critical | Integration is architecturally harder than plan states — runtime needs rich geometry |
| 4 | `autoplan` Phase 3.5 (DX) | deferred | premature | DX review blocked until integration architecture is decided |

## AUTOPLAN REVIEW REPORT

### Critical Finding: The Integration Gap

Both Claude and Codex independently found the same architectural problem:

1. **`run_external_translation_runtime()` reruns the FULL pipeline** (OCR + translate + render). It does not accept pre-computed translations. Calling it from `RenderStage` would duplicate all work and ignore `mga`'s intelligence output.

2. **The renderer needs rich geometry** that `mga` doesn't produce. The runtime's renderer consumes `ctx.text_regions` with polygon geometry, line associations, reading order, alignment/direction, and operates on `ctx.img_inpainted`. The `mga` pipeline only has `Bubble(bbox, source_text)` + `TranslationCandidate(text)`.

3. **The real seam already exists in the runtime.** `manga_translator/manga_translator.py:894` sets `ctx.agent_seam_artifact` (a `PostOCRArtifact` with full geometry). This is the correct interception point — but nothing in `mga` currently reads it.

### Correct Integration Architecture

The simplest correct path (per Codex):

```text
OPTION A: Intercept at agent_seam_artifact
  Runtime does: detect → OCR → merge → build PostOCRArtifact → SET agent_seam_artifact
  mga intercepts: read artifact → run intelligence pipeline → inject translations back
  Runtime continues: inpaint → render with mga translations

OPTION B: Override translation via text injection
  Runtime does: detect → OCR → merge → translate (overridden by mga text file) → render
  mga provides: pre-computed translations in a format the runtime can consume as override
```

Option A is architecturally cleaner but requires modifying the runtime's execution flow.
Option B is simpler but less clean — it still runs the runtime's translation step, just with overridden text.

### Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|-----------|-----------|----------|----------|
| 1 | CEO | Accept plan scope as "merge branch" | Mechanical | P6 | Branch is ready for merge at library level | — |
| 2 | CEO | Reframe: fix entry point + be honest about scope | Taste→User | P5 | User chose B: wire pipeline first | Option A (merge as-is) |
| 3 | Eng | Flag integration as harder than stated | Mechanical | P5 | Both voices confirmed independently | — |
| 4 | Eng | Identify PostOCRArtifact as correct bridge contract | Mechanical | P4 | Reuse existing runtime contract | Custom new contract |
| 5 | DX | Defer DX review | Mechanical | P3 | Premature until integration decided | — |

### Cross-Phase Themes

**Theme: The plan underestimates integration complexity** — flagged in Phase 1 (CEO) and Phase 3 (Eng). High-confidence signal. The intelligence layer is well-built but connecting it to the renderer is not a "wire two things together" task — it requires a bridge contract that preserves geometry the renderer needs.

### Deferred To TODOS.md

- Full DX review (after integration architecture is decided)
- Quality benchmarks (after end-to-end flow works)
- CI/CD pipeline setup
