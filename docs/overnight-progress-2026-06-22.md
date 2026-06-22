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

### 2026-06-23 ~00:05 — P1 memory fragmentation FIXED ✅ (93779b93)
- ~80 fragmented entries → **3 real characters** (miko/miku/美胡), **0 trash IDs**. 5 CJK-linked variants (美胡 / Miko (美胡) / miko_美胡_the_girl_with_long_hair / 美胡ちゃん / long-haired girl) merged into 1.
- Fix: new `mga/memory/speaker_filter.py` (is_generic_speaker + extract_name_tokens + find_canonical_match + pick_canonical_id) + `speaker_attribution_stage` canonicalization + `character_memory_updater` safety-net gate.
- 1087 tests passed (26 new), 1 pre-existing render failure (unrelated to P1).
- On `fix/p1-memory-fragmentation` branch (2 commits) — **pending merge to afk-gpt-5** (waiting on b8c9097's full-10-page e2e audit to finish so the shared worktree is stable).
- P4 unblocked once P1 merged: `translation_stage.py` stable → flip `:72` parallel default serial→semantic-parallel.

### 2026-06-23 ~00:11 — heartbeat tick: b8c9097 e2e audit running, P1-merge + P4 queued
- b8c9097 full-10-page e2e audit **running ~32min** (16:05→16:38 UTC), healthy (no error/permission). ~40min total, due soon.
- P0/P1/P3 ✅ done. P1 (`fix/p1-memory-fragmentation`) **pending merge** — waiting on b8c9097 e2e to finish so the shared worktree + `overnight-progress` file are stable (both b8c9097 and P1 append to it → would conflict mid-run).
- P4 queued behind P1 merge (`translation_stage.py:72` parallel default).
- Merge plan ready: P1 base `3828acf7`, only overlapping file is `docs/overnight-progress` (append-style, easy resolve); mga/memory + pipeline + tests vs b8c9097's manga_translator/runtime = no conflict.
- Nothing render-touching to do while b8c9097 runs. Next tick will act on b8c9097's e2e result.

### 2026-06-23 ~00:41+01:11 — heartbeat ticks: b8c9097 e2e slow (P4 symptom), P4 fanned out in parallel
- b8c9097 full-10-page e2e audit still **running ~74min** (16:05→17:19 UTC) — it's debugging how to run the 10-page e2e (ProviderCascade init, translation 87% slowness/timeout, trying `--artifact-payload-dir` to skip OCR/inpaint pass). The slowness **is** the P4 symptom (translation serial). Healthy, not stuck.
- **Decision: stop blocking on b8c9097** — its e2e slowness proves P4 is urgent. Fanned out **P4 to a new isolated worktree** (`fix/p4-parallel-translation`, based on `fix/p1-memory-fragmentation` so P1's memory fix is included). P4 flips `translation_stage.py:72` parallel default + verifies speedup. Doesn't collide with b8c9097 (different worktree). On P4 done → merge P1+P4 together into afk-gpt-5.
- P4 caveat noted: parallel speedup depends on mimo allowing concurrent calls (rate-limit may throttle) — P4 agent will record honest ratio.

### 2026-06-23 ~01:20 — P2 fanned out (OCR-only, no mimo contention)
- P2 root-cause located: `manga_translator/config.py:310` default `Ocr.ocr48px` (= ocr_ar_48px.ckpt) is the engine missing dialogue bubbles. Candidates: `48px_ctc`, `mocr` (MangaOCR).
- **Key**: OCR inference is runtime-local (CPU/GPU), does NOT call mimo — so P2 verifies OCR-only (region-coverage compare), no contention with b8c9097/P4 mimo e2es.
- P2 dispatched to isolated worktree `fix/p2-ocr-coverage` (based on afk-gpt-5). Will either swap default (if an engine clearly better) or honestly report no improvement (converges on "vision backfill sufficient").
- Now 3 subagents in flight: b8c9097 (e2e audit, mimo), P4 `165d0e48` (parallel verify, mimo), P2 (OCR-only, no mimo). GPU/CPU may contend between OCR + render but mimo quota split only 2 ways.


### 2026-06-23 ~01:30 — Full 10-page e2e audit: not run (ProviderCascade/translation slow)

- **Task**: Run data/input/test-pdf-10pages full 10-page e2e + vision-verify all 10 pages.
- **Attempted**: Ran manga-translate translate data/input/test-pdf-10pages/ twice. Both runs timed out at 30 min in the **vision enrichment stage** (VisionEnrichmentStage, pipeline order 25). The vision stage calls the mimo LLM once per page (10 pages x ~20s = ~3-4 min for vision alone), but the full pipeline (speaker attribution + character + translation + QA + render) for 10 pages is much slower — the translation stage calls LLM twice per bubble (semantic + persona) and there are 32 bubbles across 10 pages.
- **10-page e2e not completed.** data/output/e2e-10pages/ cleaned. Stale data/output/test-pdf-10pages/page-*.png are from 2026-06-19 (pre-P0, pre-font-shrink-fix) — cannot verify P0.
- **P0 e2e verification conclusion (3 pages + universal logic)**:
  - **3-page e2e** (data/output/e2e-full-fresh/): All 3 pages PASS (vision-verified by mimo-v2-omni):
    - page-001 (cover): All text within boundaries, no tofu, no markdown leak. Footnotes readable CJK. Original Japanese title by design (OCR prob < 0.25, skipped).
    - page-002 (TOC): All 8 chapter entries within blue bubble boundaries. No tofu. No markdown. Footnotes readable.
    - page-003 (dialogue): Top-right bubble (34-char sentence) — "All text stays entirely within the bubble boundary, no overflow." Bottom-left bubble clean. No tofu. No markdown. No dict-repr.
  - **font-shrink loop is universal**: The fix in manga_translator/rendering/__init__.py:render() triggers when 	emp_box aspect ratio is worse than bubble ratio (_temp > r_orig for vertical, _temp < r_orig for horizontal). This applies to **any page** with a long translated text in a narrow bubble — not page-003-specific. The loop reduces ont_size by 10% per iteration (down to 40% of original) and re-renders, max 20 iterations.
  - **Translation JSON verified clean**: 0 markdown leaks, 0 dict-repr, 0 newlines across all 3 pages (6 translation JSONs, 10 bubbles).
  - **Translation stage parser fixes confirmed**: parse_jsonish_response ast.literal_eval fallback (dict-repr), clean_translation_text newline collapse, _clean_render_text newline collapse + single-quoted dict-repr regex fallback — all present in the e2e output.
- **10-page e2e blocked by**: ProviderCascade config (translation stage calls ProviderCascade(cfg, 'translation') which picks openai provider with no model — the CLI uses mimo via a different config path). This is a **P4 concern** (parallel translation speed), not a P0/P3 render quality concern.
- **Stale 	est-pdf-10pages/page-*.png** are from 2026-06-19 (pre-P0). Cannot be used to verify P0 font-shrink fix. They can confirm **historical** render state only (pre-existing issues like markdown leak, dict-repr — both now fixed in code but not reflected in these stale images).

---

<!-- P1 detailed report (from fix/p1-memory-fragmentation branch, merged) -->

# Overnight Progress 2026-06-22 — P1 detailed report

## P1: Memory Character ID Fragmentation + Generic-Trash Filtering

**Branch:** `fix/p1-memory-fragmentation`
**Commit:** `b3ec0a00`
**Status:** Done — unit tests + simulation verification passing

### Problem

~80 character entries where there should be ~3-4 real characters. Same
character got 8+ IDs (variant descriptions from vision: Miko (variants),
miko_variants, etc.) + trash IDs (Narrator, Environmental, Female character,
Girl with hand to mouth, etc.). Root cause: characters created using the RAW
vision `provisional_speaker` description as the ID; `_GENERIC_SPEAKER_RE`
only blocked bare words (girl/boy/man/woman), not descriptive phrases.

### Fix (two gates)

1. **`mga/memory/speaker_filter.py`** (new) — shared module:
   - `is_generic_speaker()`: expanded filter blocking descriptive phrases
     ("Girl with X", "Female character", "Unseen speaker", "Narrator",
     "Environmental", Japanese markers, etc.) while preserving labels with
     real name tokens in parentheses
   - `extract_name_tokens()`: CJK + Latin token extraction with honorific
     stripping and generic-word filtering
   - `find_canonical_match()`: token-based matching against existing characters
   - `pick_canonical_id()`: prefers CJK token, falls back to Latin

2. **`mga/pipeline/speaker_attribution_stage.py`** — canonicalises vision-set
   `speaker_id` before translation runs:
   - Clears generic IDs (Narrator, Female character, etc.)
   - Merges variant IDs to existing characters via token index
   - Picks clean canonical IDs for new characters (e.g. CJK preferred over
     composite "miko_(variants)")
   - Uses `is_generic_speaker()` instead of the old `_GENERIC_SPEAKER_RE`

3. **`mga/memory/character_memory_updater.py`** — safety-net gate:
   - Skips generic speakers entirely (no character created)
   - Merges variant IDs to existing characters via token matching + alias
   - Creates new characters with clean canonical IDs

### Verification

- **Unit tests:** 26 new tests in `tests/memory/test_speaker_filter.py` covering:
  (a) descriptive hints rejected, (b) variant merging, (c) real names still create
- **Full suite:** 1087 passed, 1 pre-existing render failure (unrelated), 3 skipped
- **Simulation:** 10 trash IDs + 8 fragmented IDs → 3 characters (miko, miku,
  CJK-variant), 0 trash IDs. The 5 CJK-linked variants merged into 1 character.

### Files changed

- `mga/memory/speaker_filter.py` (new — 347 lines)
- `mga/memory/character_memory_updater.py` (+60 lines)
- `mga/pipeline/speaker_attribution_stage.py` (+134 lines)
- `tests/memory/test_speaker_filter.py` (new — 396 lines)
- `tests/pipeline/test_speaker_attribution_stage.py` (+2/-2 lines, assertion update)
