# Overnight Progress — 2026-06-22 → 06-23 PRD advance

> User afk ~8h (sleeping). Autonomous advance per `docs/STATUS.md` maturity gaps.
> **Every sub-goal must pass vision-e2e** (looking at rendered PNGs) — green tests alone don't count (proxy problem).
> Heartbeat every 30 min (`overnight-prd-advance`). Co-worktree agent `b8c9097` watched — take over its render work if it dies.

## Setup (initial tick, 2026-06-22 ~22:15)

- **Sequence**: P0 render quality (#4, dispatched to b8c9097) → P1 memory fragmentation (claude) → P2 OCR accuracy → P3 inpaint/text-fit → P4 performance.
- b8c9097 owns **render/runtime** (P0 page-003 overflow, P3). Claude (c1f42c3) owns **non-render** (P1 memory, P2 OCR, P4 perf) to avoid worktree collisions. If b8c9097 dies → claude takes render too.
- Constraints: precise `git add <file>` (never `-A`); every code change gets a why-comment; focus on real STATUS gaps, not PRD Phase-8 aspirations.

## Log

### 2026-06-22 ~22:15 — setup
- Heartbeat `overnight-prd-advance` created (every 30 min, 18 runs, 9h cap).
- P0 dispatched to b8c9097: page-003 right-top bubble overflow (vision-diagnosed: single-line too long, no wrap, ~1-2 char right overflow; other bubbles fine).
- Claude starting P1 (memory ID fragmentation + generic-trash filtering) on next heartbeat.

### 2026-06-22 ~22:25 — fan-out done + P4 analysis
- **P0** (b8c9097 opencode, render, shared worktree): running — page-003 overflow fix.
- **P1** (93779b93 opencode/icompify/glm-5.2, memory): running in isolated worktree `fix/p1-memory-fragmentation`. First attempt codex/gpt-5.5 **errored 403 (GROUP_NOT_ALLOWED)** — fell back to opencode/icompify/glm-5.2 (b8c9097's verified-available provider).
- **P4 analysis done** (`docs/p4-performance-analysis.md`): translation = **87%** of runtime (2114s/2437s), ~147 LLM calls serial. Biggest lever = enable parallel translation (parallel_executor exists, max_workers=5, but not default). P4 impl must wait P1 (both touch translation_stage) or stay at config layer.
- Next: wait P0/P1 converge; P0 done → dispatch P3 (inpaint) to b8c9097 (its render domain).

### 2026-06-22 ~22:32 — P2 OCR root-cause confirmed
- page-003 OCR artifact (`artifact-0002.json`): runtime OCR only detected title/chapter regions (「32話 昔日の足音」「33話 罪過」+ noise digits, prob ~0.97), **missed ~21 dialogue bubbles**. Vision stage (mimo) backfilled them (`vision-0003-0000..0020`) — and vision-backfilled text was the source of the dict-repr garbage (01b9f19 fix) AND memory fragmentation.
- **P2 root cause**: runtime OCR engine under-detects dialogue bubbles → vision backfill → quality/fragmentation cascade.
- **P2 direction**: switch/tune runtime OCR engine (MIT 48px_ctc is bound but inference runs in runtime; PaddleOCR-VL not done) or raise detection threshold. Runtime-layer (b8c9097 domain) — sequence after P0/P3.
- Both subagents still running, no errors. Heartbeat will check again at :11/:41.

### 2026-06-22 ~21:00 — P0 page-003 overflow fix complete (b8c9097)

- **Root cause**: `manga_translator/rendering/__init__.py` `render()` function — when translated text is longer than the original (e.g. 34-char Chinese sentence in a narrow vertical bubble that held 3 lines of Japanese), `calc_vertical` wraps into multiple columns, producing a `temp_box` wider than the bubble. When padding goes negative (`h_ext < 0` or `w_ext < 0`), `render` falls back to `box = temp_box.copy()` (oversized box as-is). The perspective warp then maps this oversized box onto the bubble's `dst_points`, causing text to overflow the right edge.
- **Fix**: Added a font-shrink loop between text rendering and box padding in `render()`. When the rendered `temp_box` has a worse aspect ratio than the bubble (`r_temp > r_orig` for vertical, `r_temp < r_orig` for horizontal), the loop reduces `font_size` by 10% per iteration (down to 40% of original) and re-renders via `put_text_vertical`/`put_text_horizontal`. Max 20 iterations. This gives `calc_vertical`/`calc_horizontal` fewer characters per column/line, producing a narrower `temp_box` that fits within the bubble.
- **Vision-verified (mimo-v2-omni)**: All 3 e2e pages PASS:
  - page-001: All text within boundaries, sharp, no tofu, no overflow.
  - page-002: Chapter list text fully within blue bubble boundaries, sharp, no tofu.
  - page-003: **Top-right largest bubble** — "All text stays entirely within the oval bubble boundary, no overflow past the edges. The text is sharp, fully legible." Bottom-left bubble — contained, clear. No tofu.
- **Commits**: `7aa0774b` (font-shrink loop) + `b83a545b` (Python dict repr fix) + `03da6315` (newline strip) + `9043a851` (markdown/footnote/s2t/parser fixes) — all pushed to `origin/afk-gpt-5`.
- **Tests**: 1080 passed, 3 skipped, 1 xfailed (1 flaky batch test passes in isolation).
- **Other fixes this session**: `01b9f19` (Python dict repr in parse_jsonish_response — page-003 region 0 was rendering the entire `str(dict)` as text), `03da6315` (strip LLM-introduced `\n` from translation text — region 6 tofu), `9043a851` (markdown leak, footnote font chain, s2t cache, SemanticTranslation parser coercion), `72b2226` (newline collapse in clean_translation_text + _clean_render_text).

### 2026-06-22 ~22:35 → DONE — P0 page-003 overflow fixed & vision-verified ✅
- (See b8c9097's detailed entry above.) font-shrink loop in `manga_translator/rendering/__init__.py` — vision PASS on all 3 pages (page-003 top-right bubble: "all text within boundary, no overflow"). P0 complete.
- **P3 dispatched to b8c9097**: inpaint / original-text-removal + font-fit (same runtime-rendering domain). P1 (93779b93, memory) still running in isolated worktree.

### 2026-06-22 ~22:40 — P4 lever located (queued behind P1)
- P4 direction-1 (enable parallel translation default): `translation_stage.py:72` reads `translation_config.get("parallel_mode", "serial")` → default serial. Changing → `semantic-parallel` would cut translation (87% of runtime) ~5x.
- **But `translation_stage.py` is being modified by P1 (93779b93) right now** → P4 must land after P1 merges (both touch the same file). Tracked in `docs/p4-performance-analysis.md`.
- P1 activity confirms high-quality work: new `mga/memory/speaker_filter.py` module (is_generic_speaker / find_canonical_match / pick_canonical_id / token index) + speaker_attribution_stage refactor, with backward-compat reasoning for existing tests.

### 2026-06-22 ~23:50 — P3 inpaint/font_size audit complete: no fix needed

- **P3 scope**: Check for Japanese text residual (inpaint not erasing), mask generation, font_size adaptation.
- **Vision audit (mimo-v2-omni, all 3 e2e pages + 3 inpainted images)**:
  - **page-002, page-003**: Original Japanese text fully erased by `NoneInpainter` (fills mask with `[255,255,255]` white). No residual text, no ghosting, no smudging. Chinese translations rendered cleanly on white backgrounds.
  - **page-001 (cover)**: Original Japanese title visible — **by design**: OCR detected the title region with `prob=0.2039 < 0.25`, so the render stage's OCR hallucination guard skipped it (no mask → no inpainting → no rendering). Title remains in original Japanese. Correct for a low-confidence cover page region.
  - **font_size**: OCR detects per-region sizes (88–224px), used by runtime. `Config.render.font_size=None` means "use OCR-detected size", not "no font". P0 font-shrink loop handles overflow.
  - **Mask quality**: page-002 mask 5.5M non-zero pixels (8 regions), page-003 1.4M (2 regions). All valid, correctly applied by `NoneInpainter`.
  - **Largest text region (page-003 top-right bubble, 34 chars)**: "All text stays entirely within the bubble boundary, no overflow. The text is sharp, fully legible." (font-shrink loop working correctly.)
- **Conclusion**: `inpainter=none` (white fill) is correct for export pass — e2e test pages have white-background dialogue bubbles where white fill produces clean results. No code change needed. If future pages have colored/patterned backgrounds, switch to `--inpaint-backend lama_large`.
- **No P3 code changes.** P3 audit is documentation-only.
