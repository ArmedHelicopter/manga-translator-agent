# Project STATUS — Single Source of Truth

> This is the **authoritative fact source**. Numbers are dated snapshots, not promises —
> re-run the command for current values. Do **not** hardcode these numbers in CLAUDE.md,
> README, or SPEC; reference this file instead.
>
> For aspirations (what we *want* true) use `docs/CLAIMS.md`. For the audit that produced
> this file and the doc-trust ranking, see memory `doc-trust-hierarchy`.

Last verified: 2026-06-25

## Tests

Command: `pytest tests/ -q`

| Date | passed | failed | skipped | xfailed | collected |
|---|---|---|---|---|---|
| 2026-06-22 (pre cold-start fix) | 1077 | 1† | 3 | 1 | 1080 |
| 2026-06-22 (post cold-start fix) | 1081 | 0 | 3 | 1 | 1083 |
| 2026-06-24 (focused render/profile regression suite) | 94 | 0 | 0 | 0 | 94 |
| 2026-06-25 (render/vision/artifact-cache focused) | 76 | 0 | 0 | 0 | 76 |

- **† Flaky (pre-existing, unrelated to memory cold-start):** `tests/pipeline/test_translation_stage_batch.py::test_batch_parallel_memory_consistency_across_batches` — batch-parallel memory-update ordering. Pre-sets `speaker_id="alice"`, so it bypasses SpeakerAttributionStage entirely. **Fails under one full-suite ordering, passes under another and in isolation** — test-ordering / state pollution, not a determinism bug. Passed cleanly in the post-fix full run.
- **Skips:** 2× legacy upstream (`deepl` not installed), 1× `anthropic` optional package.
- **Xfail:** `test_translation_stage_keeps_bubble_when_persona_provider_fails` (pre-existing, non-strict).

## Code metrics (machine-derived, not hand-counted)

| Metric | Value | Reproduce |
|---|---|---|
| Provider modules | 14 | `mga/providers/*_provider.py` |
| Provider preset profiles | ~40 | `registry.py::_PROVIDER_PROFILES` |
| Format adapters | 10 | `mga/format/__init__.py::_ADAPTER_REGISTRY` |
| Pipeline stages (manga / novel) | 10 / 5 | `orchestrator.py::_DEFAULT_STAGES` / `_NOVEL_STAGES` |
| QA proofreaders | 9 | `qa/orchestrator.py::_default_proofreaders` |
| Test functions | 1080 | `pytest --collect-only -q tests/` |

> CLAUDE.md / README / SPEC quote smaller stale numbers (7 or 9 stages, 6 adapters,
> "985 passing", 7/9/14 providers). This table is authoritative.

## Feature maturity (L0–L3)

L0 not started · L1 module + mock tests · L2 integration tests · L3 vision-e2e verified on rendered PNGs.

| Feature | L | Note |
|---|---|---|
| Provider cascade | 3 | wired, tested |
| Format adapters (documented 6) | 3 | all present |
| Novel adapters (undocumented 4) | 2 | exist, lighter tests |
| QA proofreaders (9) | 2 | wired; markdown-leak slipped through → e2e guard needed |
| Page footnotes | 2 | CJK tofu on Windows fixed 2026-06-22 |
| OCR guard + recovery | 2 | module + tests; real-corpus accuracy 47% vs >98% target |
| Distill (Card / Lorebook / Hermes) | 2 | exporters + importers present |
| Re-inpaint Pass 2 + artifact pin + per-page payload alignment | 3 | `recon-fresh-20260624-v4` TE-01..TE-04 passed: no -1 shift, no tail base-plate reuse. **Fallback-only vision injection** (commit `de1642cd`): render-only re-verify 2026-06-25 — OCR-only artifacts restored (page-005 6→4, page-006 4→3 regions), vision QA confirms text inside bubbles, no white blocks |
| Learning engine (L1–L4) | 1 | modules + mock tests; real hot-start loop unverified (PRD §4.2.1) |
| Memory / wiki + CharacterGraph | 2 | active — `CharacterMemoryUpdater` writes real profiles (美胡/Miku, 2026-06-21 e2e) |
| **Character consistency (headline value)** | 2 | memory non-empty & updater active; **new gap: ID fragmentation + generic-trash IDs** (see `docs/handoff-2026-06-22-memory-reassessment.md`) |
| Web UI | 2 | 3255 lines FastAPI + React; undocumented in CLAUDE.md |
| MCP server / plugin system | 1 | files exist; SPEC Phase-8 `[x]` unverified |
| Incremental / batch as CLI entry | 1 | modules exist; not the default main chain (ROADMAP) |

## E2E verification snapshots

| Date | Fixture | Output | Models / concurrency | Result |
|---|---|---|---|---|
| 2026-06-24 | `data/input/test-pdf-10pages` | `data/output/recon-fresh-20260624-v4` | vision `icompify/minimax-m3`, translation `icompify/deepseek-v4-pro`, CLI concurrency 8 | TE-01..TE-04 passed; page-003 shaved-ice cover, page-004 contents, page-009/010 distinct base plates |
| 2026-06-25 (render-only re-verify) | `data/input/test-pdf-10pages` | `data/output/e2e-fix-20260625` | current code, **no re-translation** (`run_render_only` from the v4 payload; `ICOMPIFY_API_KEY` unset) | fallback-only guard proven: OCR-only artifacts restored (vision seats dropped), full-res vision QA — translated text inside speech bubbles on pages 005/006, no white occlusion boxes |

Artifacts: `te-verification-summary.json`, `te-vision-verification-minimax-m3.json`, and `verification_contact_sheet.png` in the output directory.

## Performance vs target (PRD §6)

| Metric | Target | Observed (10-page e2e, 2026-06-19) | Status |
|---|---|---|---|
| Per-page time | < 30s | ~244s | ❌ ~8× over |
| OCR accuracy | > 98% | 47% (47/100 regions) | ❌ |
| Translation parallel speedup | ~5× (semantic-parallel) | **UNVERIFIED** — mimo token-plan throttles concurrency (default reverted to serial); no high-concurrency provider tested | ⚠️ theoretical only |

## Repository state & history

- **`afk-gpt-5` is live on origin** (2026-06-22). History was rewritten with `git filter-repo`
  to strip the entire `models/` runtime-weight directory (3 `.ckpt` files >100MB, mis-committed
  in `83d5ef6` "wip: mga-layer-bootstrap WIP snapshot", which blocked push). All commit content
  preserved; only `models/` paths removed, hashes changed. See
  `docs/handoff-2026-06-22-history-rewrite.md`.
- **Local aligned** to `origin/afk-gpt-5` (HEAD `b83a545b`). The other worktree agent's unpushed
  commit (dict-repr fix) was cherry-picked back onto the new history, then pushed.
- **`models/` is a symlink, not in git**: `models` → main repo's `models/` (old history still
  has the weights). Runtime needs it for e2e. `.gitignore` `/models` keeps it untracked.
  **Runtime model weights are managed externally, never committed** — a fresh clone must restore
  `models/` (symlink or copy from the main repo, or re-download).

## Current focus

Rendering-layer e2e quality closure is now verified for the 10-page alignment fixture: `recon-fresh-20260624-v4` passed TE-01..TE-04 with native vision evaluation. The v4 run also exposed a **text-outside-bubbles regression** (host-side vision bboxes injected onto OCR-populated pages → white occlusion boxes); fixed by fallback-only vision injection (commit `de1642cd`) and re-verified 2026-06-25 via render-only re-run with full-res vision QA. Continue to treat rendered PNG vision review as the binding signal for future render changes — the **proxy problem** remains a governance rule even when unit tests are green (`docs/e2e-testing.md`).

## Governance rules

1. **Don't hardcode counts in prose docs.** Reference this file or the reproduce command.
2. **CLAIMS vs STATUS separation.** Aspirations → `docs/CLAIMS.md`; only verified facts here.
3. **Maturity label, not `[x]`.** SPEC's `[x]` re-interprets as L1/L2 here; only vision-e2e-verified features reach L3.
4. **CI guard (proposed):** a check that runs `pytest --collect-only -q tests/` and diffs the count against the latest snapshot row above, failing on drift — prevents silent staleness returning.
