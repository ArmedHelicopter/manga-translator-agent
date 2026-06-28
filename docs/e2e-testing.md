# End-to-End (E2E) Testing

## What the e2e test is

The e2e test runs the **full manga translation pipeline** on a representative sample and inspects the **actually rendered images** — not just intermediate JSON or unit tests.

Pipeline stages (in order): `format → ocr_artifact → ocr_guard → vision → speaker_attribution → character → character_memory → translation → qa → render`.

- **Input**: use the smallest representative set for quick smoke (`data/input/e2e-3pages/`) and the 10-page alignment fixture (`data/input/test-pdf-10pages/`) for page-to-payload mapping regressions.
- **Runtime**: external-two-pass, render-only mode. mga invokes the worktree-local `manga_translator/` via `python -m manga_translator` with `cwd=project_root`.
- **Provider**: configured in `configs/providers.toml`; the 2026-06-24 alignment run used `icompify/minimax-m3` for vision and `icompify/deepseek-v4-pro` for translation with CLI concurrency 8.
- **Output**: rendered `page-*.png`, `.mga-payload/artifact-NNNN.json`, `.mga-payload/inpainted-NNNN.png`, `.mga-payload/translations-NNNN.json`, `.mga-payload/pages.json`, `manifest.json`, `run.json`, and `qa_report.json` when present.

The e2e test is the **ground truth** for whether a change actually fixes a rendering/translation defect. Unit tests can be green while the rendered images are still broken — this has happened (the markdown-leak + footnote-tofu regression shipped with a green suite).

## Encoding and Unicode verification on Windows

PowerShell/stdout is not a reliable Unicode verifier on this project. It may show CJK/Japanese text as `??` or mojibake even when the underlying UTF-8 JSON and rendered PNG are correct. Treat console output as a transport/display layer, not as the source of truth.

Use these checks instead:

```powershell
# Inspect JSON as UTF-8 bytes, then parse it.
.\.venv\Scripts\python.exe -c "import json, pathlib; p=pathlib.Path(r'data/output/OUT/.mga-payload/translations-0000.json'); data=json.loads(p.read_bytes().decode('utf-8')); print(repr(data))"

# Inspect exact codepoints when the console display is suspect.
.\.venv\Scripts\python.exe -c "s='\u6d4b\u8bd5'; print([hex(ord(c)) for c in s])"
```

For temporary verification scripts, avoid sending literal non-ASCII fixtures through PowerShell here-strings or stdin. Prefer `\uXXXX` string escapes in the Python code, or read a UTF-8 file explicitly with `encoding="utf-8"`. For rendered output, crop/open the `page-*.png` or use a vision-capable model; do not infer glyph correctness from terminal text.

## How to run it

```powershell
cd C:\Users\Administrator\.paseo\worktrees\manual-afk-gpt-5-manga-translator-agent-local-head
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# Force a FRESH run (do not let stale cache / pinned artifacts mask the fix):
#   - move .mga_cache\llm_cache.db aside (or clear the relevant entries), and
#   - delete .mga_cache\artifact-pin.json

# Quick 3-page smoke
manga-translate translate data/input/e2e-3pages/ -o data/output/e2e-full-fresh --config configs/providers.toml

# 10-page page-to-payload alignment regression (high concurrency)
manga-translate translate data/input/test-pdf-10pages -o data/output/recon-fresh-YYYYMMDD `
  --config configs/providers.toml --provider icompify `
  --parallel-mode semantic-parallel --concurrency 8 --verbose
```

Always run into a **new output dir** when validating a fix, so you compare against freshly rendered images rather than a stale directory. Before creating a new validation output under `data/output/`, delete the oldest disposable generated output directory first; keep canonical evidence dirs that are referenced below or in `docs/STATUS.md`.

## How to evaluate results (binding rule)

**E2E results MUST be evaluated by a vision-capable model looking directly at the rendered `page-*.png`.**

Do **not** evaluate by:
- pixel diff against a reference image,
- pixel statistics / histogram / hash heuristics, or
- unit tests / JSON-field assertions alone.

**Why — the proxy problem.** Those are proxy metrics. They cannot detect the real failure modes: markdown labels rendered into the text (`**Corrected Translation:** …`), tofu boxes from missing CJK fonts, wrong text orientation, or semantic mistranslation. A pixel-diff or unit-test "pass" does not mean the page looks right. The regression documented in `docs/handoff-2026-06-22-e2e-regression.md` shipped precisely because the suite was green while the images were broken — the agent trusted a proxy signal instead of looking at the images.

**Procedure:**
1. Open each rendered `page-*.png`.
2. Have a **vision-capable model** (e.g. `mimo-v2.5` vision, or any multimodal model) verify, per page: is the rendered text readable CJK? any markdown/label leakage? any tofu/missing-glyph boxes? correct text orientation? are the translations sensible in context?
3. Record the vision verdict per page. A page passes **only** if the vision model confirms the rendered output is correct.

If the reviewing agent itself has a vision modality, it can look at the images directly; otherwise it must call a vision model on each PNG. Either way, the pass/fail signal is the vision judgment of the rendered image — never a computed pixel metric.

## Verified alignment run

2026-06-24: `data/output/recon-fresh-20260624-v4/` is the current 10-page alignment proof run.

- Command: `manga-translate translate data/input/test-pdf-10pages -o data/output/recon-fresh-20260624-v4 --config configs/providers.toml --provider icompify --parallel-mode semantic-parallel --concurrency 8 --verbose`.
- Models: vision `icompify/minimax-m3`; translation/persona render `icompify/deepseek-v4-pro` from `configs/providers.toml`.
- TE summary: `data/output/recon-fresh-20260624-v4/te-verification-summary.json` reports TE-01..TE-04 passed.
- Native vision evidence: `data/output/recon-fresh-20260624-v4/te-vision-verification-minimax-m3.json` confirms `page-003` is the two-girls shaved-ice page, `page-004` is the contents page, and `page-009` / `page-010` do not share a base plate.
- Visual audit sheet: `data/output/recon-fresh-20260624-v4/verification_contact_sheet.png`.

## Verified render-regression closure

2026-06-26: `data/output/e2e-verify-20260626-v2/` was a partial 10-page render-quality proof run for the empty-pin and mixed OCR+vision regressions. It is no longer the closure run: later visual review found page-007 near-duplicate vision text and no-translation artifact/inpaint fallout were not covered.

- Command: `.\.venv\Scripts\manga-translate.exe translate data\input\test-pdf-10pages -o data\output\e2e-verify-20260626-v2 --config configs\providers.toml --provider icompify --parallel-mode semantic-parallel --concurrency 8 --verbose`.
- Run summary: `run.json` completed with `error_count=0`, `page_count=10`, runtime `pages_rendered=10`, and `translation_count=65`.
- Page-010 pin recovery evidence: `.mga-payload/artifact-0009.json` has 9 valid OCR regions and `.mga-payload/translations-0009.json` has 9 non-empty translations, so the stale empty pin no longer erases source text into empty bubbles.
- Mixed vision evidence: `.mga-payload/artifact-0004.json` has only the two OCR regions for page-005; the duplicate same-source vision seat that previously rendered text outside the bubble is skipped.
- Direct visual audit: pages 005, 006, 009, and 010 were inspected as rendered PNGs. Text is inside speech bubbles; page-010 no longer has mass empty bubbles; page-005 no longer has duplicated out-of-bubble text; pages 006 and 009 do not show large white occlusion boxes.

2026-06-27: `data/output/e2e-overflow-fix-20260627-v2/` was superseded. A later manual visual audit found `page-007` still had left-side leaked text and `page-009` could still receive vision/SFX-derived render seats, so do not use v2 as closure evidence.

- Command: `.\.venv\Scripts\manga-translate.exe translate data\input\test-pdf-10pages -o data\output\e2e-overflow-fix-20260627-v2 --config configs\providers.toml --provider icompify --parallel-mode semantic-parallel --concurrency 8 --verbose`.
- Run summary: `run.json` completed with `error_count=0`, `page_count=10`, runtime `pages_rendered=10`, and `translation_count=63`.
- Payload invariant: after render-stage pruning, pages without rendered dialogue (`0000`, `0001`, `0002`, `0003`, `0007`) have `regs=0 trans=0 fns=0`; rendered dialogue pages have `len(artifact.text_regions) == len(translations)` and contiguous `region_index` values.
- Historical note: v2 helped expose the remaining failure shape, but its written "page-007 fixed" conclusion was wrong because the crop inspected the wrong area.

2026-06-27: `data/output/e2e-overflow-fix-20260627-v4/` was superseded by v5. It fixed the page-007 leak, page-009 SFX-over-art regression, and page-010 mass-empty-bubble regression, but a later all-page visual audit found the color pages were red/blue channel-swapped in the final render output.

- Command: `.\.venv\Scripts\manga-translate.exe translate data\input\test-pdf-10pages -o data\output\e2e-overflow-fix-20260627-v4 --config configs\providers.toml --provider icompify --parallel-mode semantic-parallel --concurrency 8`.
- Run summary: `run.json` completed with `error_count=0`, `page_count=10`, runtime `pages_rendered=10`, and `translation_count=38`.
- Payload invariant: pages without rendered dialogue (`0000`, `0001`, `0002`, `0003`, `0004`, `0007`) have `regs=0 trans=0 fns=0`; rendered dialogue pages have matching artifact/translation region counts.
- Page-007 evidence: `.mga-payload/artifact-0006.json` has 3 OCR regions and `.mga-payload/translations-0006.json` has 3 translations. Direct inspection of `_crop_page007_bottom_left.png` confirms the left-bottom bubble text stays inside the balloon instead of leaking left.
- Page-009 evidence: `.mga-payload/artifact-0008.json` has 4 rendered regions and no SFX/body overlay seat. Direct inspection of `_crop_page009_upper_left.png` confirms the previous Chinese SFX text over the character/body is gone.
- Page-010 evidence: `.mga-payload/artifact-0009.json` has 9 text regions and `.mga-payload/translations-0009.json` has 9 translations. Direct inspection of `_crop_page010_full.png` confirms the old mass empty bubbles are filled.
- Full visual audit sheet: `data/output/e2e-overflow-fix-20260627-v4/_input-output-audit-current.png`.

2026-06-27: `data/output/e2e-overflow-fix-20260627-v5/` is the visual closure run for the page-007 leak, page-009 SFX-over-art regression, page-010 mass-empty-bubble regression, and color-channel regression. It is not full title/contents closure; later review found page-008 and page-004 title/contents text still needed translation coverage.

- Command: `.\.venv\Scripts\manga-translate.exe translate data\input\test-pdf-10pages -o data\output\e2e-overflow-fix-20260627-v5 --config configs\providers.toml --provider icompify --parallel-mode semantic-parallel --concurrency 8`.
- Run summary: `run.json` completed with `error_count=0` and `translation_count=55`; all 10 `page-NNN.png` outputs exist.
- Color evidence: RGB means match input on color pages after the runtime PIL output fix (`page-001` input/output `[164.7, 107.6, 94.1]`, `page-003` input/output `[169.3, 112.2, 112.3]`), so the v4 blue tint is gone.
- Visual audit: all pages 001-010 were inspected from `_input-output-audit-current.png`; pages 001-004 preserve cover/back/color insert/contents art without large Chinese overlays or blue tint, pages 005-006 render inside speech bubbles, and page-010 no longer has mass empty bubbles. Do not reuse the old "page-008 title art is not re-typeset" conclusion as success criteria: title/contents pages with translatable entries must be translated.
- Page-007 evidence: direct inspection of `page-007.png` confirms the left-side and left-bottom bubble text stays inside the balloons instead of leaking into the left margin/art.
- Page-009 evidence: direct inspection of `page-009.png` confirms no Chinese SFX/vision text is rendered over the character/body; original non-bubble SFX remains as source art.
- Full visual audit sheet: `data/output/e2e-overflow-fix-20260627-v5/_input-output-audit-current.png`.

2026-06-28: `data/output/e2e-render-current-20260628-footnotes-on-v2/` is the current render-only visual proof for the title/contents follow-up and explicit footnote rendering. The paired default-footnote check is `data/output/e2e-render-current-20260628-default/`.

- Scope: render-only verification from the current 10-page payload after deleting the oldest disposable output dir (`data/output/e2e-10-fresh`) before creating the new output.
- Page-004 evidence: `.mga-payload/translations-0003.json` renders the contents entry as `第34话 恸愧之鞭`; direct inspection of `page-004.png` confirms the title appears under `第34话`.
- Page-005 and page-008 evidence: direct visual inspection confirms both pages have translated rendered text, so title/chapter pages are no longer treated as automatically suppressible.
- Regression evidence: direct visual inspection confirms page-007 has no left-side text leak, page-009 has no body/face text leak, and page-010 has no mass empty bubbles.
- Footnote evidence: default render omits page footnotes (`fns=0`); explicit `render_footnotes=True` renders readable footers on pages 005, 009, and 010 with no `??` or tofu boxes.
