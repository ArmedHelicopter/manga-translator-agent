# [Handoff] Fix e2e regression: markdown leak + garbled footnotes

Originated 2026-06-22. Previous agent (`claude/glm-5.2[1M]`, paseo agent `540b7e61`, claude session `e98b528d`) reported success but the actual rendered output still has both regressions. Its last turn ended on a provider 500 overload (`glm-5.2` gateway: “该模型当前访问量过大”) — unrelated to code.

## Task

Continue the autonomous e2e fix loop. The previous agent **believed it was done** (claimed “237 tests pass, no regression, I read every rendered image, all good”) but the user looked at the same output and the two bugs are still there. Your job: find out **why the existing fixes did not reach the real rendered output**, then actually fix and re-verify against the **real rendered images** (NOT just unit tests).

Carry the user’s exact directive/intent:
> 启动端到端测试，不要老问我，有问题就修复，不要管范围；to be more efficient, you should fan out subagents; 最近的一次测试 `data/output/e2e-full` 中 page-003 出现了明显的 markdown 语法（不符合漫画翻译要求），而且所有图片的脚注都变成乱码了，这个问题明明之前修复过，怎么又出现了？

i.e. run autonomously, fix without asking, fan out subagents, don’t limit scope.

## Context

- **Project**: `mga` (Manga Translate Agent) — intelligence/orchestration/QA/memory layer. Uses `manga-image-translator` as the rendering runtime via subprocess (external-first, PRD §1.2.2). Pipeline: `Format → OCR → ocr_guard → Vision → Speaker → Character → character_memory → Translation → QA → Render → Output`.
- **Worktree**: `C:\Users\Administrator\.paseo\worktrees\manual-afk-gpt-5-manga-translator-agent-local-head`, branch `afk-gpt-5`. Python venv `.venv` (3.12). Read `CLAUDE.md` for the full architecture.
- **Runtime mga invokes**: the **top-level `manga_translator/`** in this worktree. `run_export_artifact`/`run_render_only` run `python -m manga_translator` with `cwd=project_root`, using this worktree-local copy (the code explicitly prefers it over any external clone — see `mga/runtime_bridge/external.py`). It is a normal directory and **directly editable**.
- **Translation provider**: mimo (`mimo-v2.5` / `mimo-v2.5-pro`) via OpenAI-compatible endpoint. API key hardcoded in `mga/providers/factory.py::_PROVIDER_PROFILES`. Config in `configs/providers.toml`.

## The two regressions (CONFIRMED in the real output)

Latest e2e run: `data/output/e2e-full/` — 3 pages (cover + TOC + content), 11 translations, `run.json` status=completed, 0 errors, **written 2026-06-22 08:24 local**.

### Regression 1 — markdown label leaks into rendered translation text
- **Evidence**: `data/output/e2e-full/translations/page_0001.json`, bubble `region-0001-0005`:
  `text = "**Corrected Translation:** 第35话 那框住阳光的事物"` — the `**Corrected Translation:**` markdown label is stored verbatim and rendered onto the image.
  (User said “page-003”. Note the 1-based/0-based trap: `page-NNN.png` is 1-based, translation index is 0-based. `page-003.png` = `page_0002.json`. The markdown above is on the TOC page `page_0001.json` = `page-002.png`. **Sweep ALL pages** for `**` / label leakage, don’t fix only one.)
- **Source**: QA re-translate path emits markdown labels; they flow through `RenderStage._extract_render_text`, which did not strip them.
- **A fix ALREADY EXISTS (uncommitted)** in `mga/pipeline/render_stage.py`: new `_clean_render_text()` → `_strip_llm_chatter()` strips leading `**Label:**`, plain `Label:`, and wrapping `**…**`. See `git diff`.
- **WHY it still leaks in e2e-full**: the e2e-full output was written **08:24 local**, the `_clean_render_text` refactor landed **~08:37 local** — **e2e-full predates the fix by ~13 minutes**. The previous agent then claimed a clean re-run at 11:11 local but **e2e-full was never rewritten** (still 08:24). Likely cause: `.mga_cache/llm_cache.db` (grew 98 KB → 622 KB) + the new artifact pinning (`pin_artifacts=True`, see `mga/runtime_bridge/artifact_cache.py`) made the “re-run” serve cached translations and skip re-render.
- **Action**: force a genuinely fresh re-run into a NEW output dir; verify the markdown is gone in the NEW rendered images. Do not trust the stale `e2e-full`.

### Regression 2 — garbled footnotes (tofu / 乱码) on all images
- **Root cause** (per `docs/plans/e2e-render-fix-plan-2026-06-22.md` §4.1): footnotes are DRAWN by the runtime in `manga_translator/manga_translator.py::_draw_footnotes` (fonts at ~L787-792: two hardcoded Linux Noto paths → on Windows `ImageFont.load_default()` → tofu boxes). This is the top-level `manga_translator/` copy that mga actually invokes. The CJK font `fonts/msyh.ttc` (≈19.6 MB) IS present in the repo root; the bubble renderer's `FALLBACK_FONTS` (`text_render.py`) already uses it.
- **Constraint**: modifying the local runtime is **allowed** (PRD §1.2.2; `docs/render_purity_contract.md` Edit scope). You may directly patch `manga_translator/manga_translator.py::_draw_footnotes` (e.g. font chain → `fonts/msyh.ttc` → `Arial-Unicode-Regular.ttf` → `msgothic.ttc` → `C:/Windows/Fonts/msyh.ttc` → Linux Noto → `load_default()`). Prefer an mga-side fix when feasible (pass font_path via the runtime `render_config`/payload, or post-render overlay); otherwise patch `manga_translator/`.

## Relevant files
- `mga/pipeline/render_stage.py` — `RenderStage`: `_extract_render_text`, `_clean_render_text`, `_strip_llm_chatter`, `_strip_inline_footnote_noise`, `_write_page_translations`, OCR hallucination guard, artifact pinning. **Uncommitted +278 lines.**
- `mga/pipeline/vision_stage.py` — **uncommitted +497 lines**; per the prior agent these introduced failures in `tests/pipeline/test_ocr_vision_split.py` and `test_vision_supplement.py`. Investigate before trusting.
- `mga/pipeline/parsers.py` — `_clean_translation_text`, `parse_translation_response` (markdown leaks also originate upstream here).
- `mga/runtime_bridge/artifact_cache.py` — `ArtifactPin`, `resolve_pinned_artifact` (NEW, untracked). Content-addressed pin on `sha256(I_n)`, store at `<working_dir>/.mga_cache/artifact-pin.json`.
- `mga/runtime_bridge/external.py` — runtime subprocess invocation; `run_export_artifact`, inpainter selection.
- `manga_translator/manga_translator.py::_draw_footnotes` (RUNTIME actually invoked — top-level `manga_translator/`, run via `python -m manga_translator`; fonts ~L787-792) — footnote font. Modifying the local runtime is allowed; prefer mga-side, else patch here.
- `docs/render_purity_contract.md` — the runtime-authoritative contract (Edit scope: modifying the local runtime is allowed).
- `docs/handoff-2026-06-19-pipeline-run.md` — earlier handoff (5 bugs fixed in parsers/render_stage/external/cli).
- `docs/plans/e2e-render-fix-plan-2026-06-22.md` — comprehensive 5-category root-cause plan.
- `data/output/e2e-full/` — the failing output (`translations/page_000*.json`, `.mga-payload/translations-000*.json`, `manifest.json`, `run.json`, `qa_report.json`, `page-00*.png`).

## Current state
- Uncommitted: `render_stage.py` (+278), `vision_stage.py` (+497), `.mga_cache/llm_cache.db`, `test/testdata/render/default1.png`.
- Then-untracked: `FIX_PLAN.md` (now `docs/plans/e2e-render-fix-plan-2026-06-22.md`), `docs/render_purity_contract.md`, `docs/handoff-2026-06-19-pipeline-run.md`, `mga/runtime_bridge/artifact_cache.py`, `verify_reinpaint.py` (now `scripts/verification/verify_reinpaint.py`), several new tests (`tests/pipeline/test_render_stage_*.py`, `tests/runtime_bridge/test_artifact_cache.py`, …).
- Suite was reported “237 passing, no regression” — **green tests do NOT imply clean output** (tests were green while images still leaked markdown). Do not trust test-green alone; always eyeball the rendered PNGs.

## What was tried
- `_clean_render_text` / `_strip_llm_chatter` added to strip markdown labels at render time (uncommitted). The regex handles `**Corrected Translation:**` correctly in isolation — but was never validated against a fresh e2e render because the re-run was cache-skipped.
- Artifact pinning + OCR hallucination guard added (render-purity work).
- Earlier (2026-06-19): `_clean_translation_text` in parsers.py; `_page_bubble_id` matching both `region-` and `vision-` prefixes; `ast.literal_eval` fallback; RATIONALE_TERM_RE Unicode fix.
- Footnote font fix was PLANNED (`docs/plans/e2e-render-fix-plan-2026-06-22.md` §4.1) as a `manga_translator.py::_draw_footnotes` edit (the correct, invoked file) but never landed — blocked by the old mga-only contract. That constraint is now lifted: patch `manga_translator/manga_translator.py::_draw_footnotes` directly.

## Decisions / constraints
- **Edit scope**: `mga/` is primary, but modifying the local runtime (`manga_translator/`) is **allowed** when a real runtime bug blocks delivery. Prefer mga-side; else patch `manga_translator/`. Runtime remains authoritative for **geometry** (OCR artifact); mga = intelligence.
- Runtime artifact (`artifact-NNNN.json` text_regions) is authoritative geometry; mga does not override OCR geometry.
- Carry the user’s intent: autonomous, fan out subagents, fix without asking, don’t limit scope.

## Acceptance criteria
- [ ] Force a FRESH e2e run into a new output dir. To actually bypass caching: clear the relevant entries in `.mga_cache/llm_cache.db` (or move it aside) AND delete the pin sidecar `.mga_cache/artifact-pin.json`, then re-run. Do not re-read the stale `e2e-full`.
- [ ] Zero markdown in any `translations/page_*.json` text — grep for `**`, `Corrected Translation`, `译文：`/`译文:`, leading `#` / `- ` / `* `.
- [ ] Rendered footnote text is readable CJK on every page that has footnotes (no tofu boxes) — verify by eye on the actual `page-*.png`.
- [ ] **Evaluate every rendered page with a vision-capable model looking directly at the PNG.** Do NOT use pixel diff / pixel statistics / unit tests as the pass signal — that is the proxy problem (a green suite while the images are broken is exactly what happened here). See `docs/e2e-testing.md`.
- [ ] `pytest tests/` green with no new regressions (investigate the `vision_stage.py`-related failures; don’t leave them red).
- [ ] Report the exact mechanism that made footnotes render correctly (mga-side font passing, or a `manga_translator/` patch).

## How to run
```powershell
cd C:\Users\Administrator\.paseo\worktrees\manual-afk-gpt-5-manga-translator-agent-local-head
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest tests\ -v
# Inspect data/output/e2e-full/run.json for the exact e2e invocation + input dir, then re-run into a fresh dir, e.g.:
.\.venv\Scripts\manga-translate.exe data/input/<sample> -o data/output/e2e-full-fresh
```
