# Pipeline Run Handoff: 10-Page Manga Translation (2026-06-19)

## Context

This document summarizes the full pipeline run of 10 pages from `私を喰べたい、ひとでなし(8)` PDF, the bugs found and fixed, and the current state of the output.

## Worktree

- **Path**: `C:\Users\Administrator\.paseo\worktrees\manual-afk-gpt-5-manga-translator-agent-local-head`
- **Git**: Yes (has uncommitted changes in `mga/pipeline/parsers.py`, `mga/pipeline/render_stage.py`, `mga/runtime_bridge/external.py`, `mga/cli/main.py`)

## Input

- **PDF**: `私を喰べたい、ひとでなし(8) (電撃コミックスNEXT) (苗川采)` (135 MB, 186 pages)
- **Pages extracted**: 10 (page 1–10, rendered at 200 DPI from PDF)
- **Input dir**: `data/input/test-pdf-10pages/` (10 PNG files, no subdirs)

## Output

- **Output dir**: `data/output/test-pdf-10pages/`
- **Output structure**:
  ```
  test-pdf-10pages/
  ├── page-001.png ~ page-010.png    (10 rendered translation images)
  ├── translations/                  (10 per-page translation JSONs)
  ├── metadata/                      (manifest.json, run.json, qa_report.json, translation-report.json)
  ├── .mga-payload/                   (52 files: artifacts, inpainted, masks, pages, translations)
  └── logs/                          (134 log files)
  ```

## Pipeline Run Summary

| Metric | Value |
|---|---|
| Status | completed |
| Page count | 10 |
| Translation count | 70 |
| Errors | 0 |
| Total time | 2437s (40.6 min) |
| Provider | mimo (mimo-v2.5) |
| Source lang | ja |
| Target lang | zh-CN |

### Stage timings

| Stage | Time |
|---|---|
| format | 0.0s |
| ocr_artifact | 0.0s |
| ocr_guard | 0.0s |
| vision | 185.7s |
| speaker_attribution | 0.0s |
| character | 0.0s |
| translation | 2114.5s |
| qa | 70.1s |
| render | 56.0s |
| output | 0.0s |

## Bugs Found and Fixed

### Bug 1: `parse_jsonish_response` doesn't parse Python dict repr (single quotes)

**File**: `mga/pipeline/parsers.py`
**Symptom**: LLM returned `{'text': '...', 'persona_moves': [...]}` (Python dict repr with single quotes). `json.loads()` failed → `parsed=None` → entire 388-char string used as translation text.
**Root cause**: `json.loads()` only accepts double-quoted JSON. Python dict repr uses single quotes.
**Fix**: Added `ast.literal_eval()` fallback after JSON parse failure. Applied to both top-level and embedded dict detection.
**Impact**: 6/75 translations (8%) had garbage text (Python dict repr). After fix: 0/70 (0%).

### Bug 2: QA stage markdown prefix leaks into translation text

**File**: `mga/pipeline/parsers.py`
**Symptom**: QA returned `**Corrected translation:** 第34話` — the entire markdown was stored as translation text.
**Root cause**: `parse_translation_response` fallback path stored raw text without stripping markdown.
**Fix**: Added `_clean_translation_text()` function that strips:
- `**Corrected translation:**` prefix
- `**Translation:**` prefix
- `**Explanation:**` suffix (and everything after)
- `**Note:**` suffix
- `**Rationale:**` suffix
Applied to all return paths in `parse_translation_response`, `parse_semantic_response`, `parse_persona_response`.
**Impact**: 1/75 translations (1.3%) had markdown prefix. After fix: 0/70 (0%).

### Bug 3: `TEXT_FIELD_RE` / `FOOTNOTE_ITEM_RE` only matched double quotes

**File**: `mga/pipeline/parsers.py`
**Symptom**: `extract_structured_from_malformed()` couldn't extract text from Python dict repr.
**Root cause**: Regex patterns only matched `"text":"..."` (double quotes), not `'text':'...'` (single quotes).
**Fix**: Updated `TEXT_FIELD_RE` and `FOOTNOTE_ITEM_RE` to match both `"` and `'` quotes.

### Bug 4: `RenderStage._write_page_translations` only matched `region-` prefix bubbles, dropping `vision-` prefix bubbles

**File**: `mga/pipeline/render_stage.py`
**Symptom**: Page 10 (index 9) had 0 text_regions from OCR, all 7 bubbles came from vision_enrichment (`vision-0009-*`). RenderStage only matched `region-0009-` prefix → 0 translations written → page rendered blank.
**Root cause**: `_write_page_translations` used `prefix = f"region-{page_idx:04d}-"` to filter translations. Vision-enriched bubbles have `vision-{page_idx:04d}-` prefix.
**Impact**: 43/75 translations (57%) were dropped in render stage. Page 10 rendered blank (no translated text). After fix: 0/70 dropped, all pages rendered with text.
**Fix**: Added `_page_bubble_id()` helper that matches both `region-` and `vision-` prefixes. Updated `source_by_bubble` dict and translation filter loop to use it.

### Bug 5: `RATIONALE_TERM_RE` regex corrupted (Unicode characters lost)

**File**: `mga/pipeline/parsers.py`
**Symptom**: Line 114 had garbled characters instead of `「」『』`.
**Root cause**: Edit tool corrupted Unicode characters in the regex.
**Fix**: Reconstructed correct regex with `chr(0x300C)` + `chr(0x300E)` for left brackets and `chr(0x300D)` + `chr(0x300F)` for right brackets.

## Bugs Found (NOT Fixed — manga_translator Runtime)

### Runtime Bug 1: `inpainter: none` — no text erasure

**Cause**: `run_export_artifact` sets `effective_inpainter = "none"` when `inpaint_backend == "auto"`. manga_translator generates masks but doesn't inpaint.
**Impact**: Original text partially visible under rendered translation.
**Fix**: Change `inpainter` to `original` (OpenCV simple fill, no model needed) or download lama_large/lama_mpe model files.
**Status**: Config change (`--inpaint-backend original`), not code fix. Requires re-running Pass 1 to take effect.

### Runtime Bug 2: OCR direction detection `auto` → horizontal

**Cause**: Model48pxOCR detects `direction: auto` for all text regions. For vertical Japanese text (table of contents), renderer outputs horizontal text.
**Impact**: Table of contents pages (page 3) have horizontal text instead of vertical.
**Fix**: Not fixable at mga level — this is manga_translator OCR behavior. Could work around by post-processing `artifact-*.json` to force `direction: vertical` for specific pages.

### Runtime Bug 3: `font_size: None` / `font_size_minimum: -1`

**Cause**: artifact `render_config` has `font_size: None`, `font_size_minimum: -1`. manga_translator uses default font.
**Impact**: Font rendering is basic sans-serif, not manga-appropriate.
**Fix**: Config change in `render_config`, not mga code.

### Runtime Bug 4: Memory not produced

**Cause**: `speaker_attribution` stage found all bubbles have `speaker_id=None`. `_update_profiles` skips when no speakers detected.
**Impact**: No character profiles or memory state.
**Fix**: Not a bug — correct behavior when speaker info is absent. Enhancement: add speaker detection in vision_enrichment.

## Environment

- **Python**: 3.12.6 (`.venv`)
- **Provider**: mimo (mimo-v2.5) via OpenAI-compatible API at `https://token-plan-cn.xiaomimomo.com/v1`
- **API key**: Stored in `_PROVIDER_PROFILES` dict in `mga/providers/factory.py` (hardcoded, not env var)
- **Config**: `configs/providers.toml` (vision: mimo-v2.5, translation: mimo-v2.5-pro, qa: mimo-v2.5-pro)
- **GPU**: CUDA 11.8 available (but not used by manga_translator for inpainting)
- **Models**: `ocr_ar_48px.ckpt` (200MB) present in `models/ocr/`; lama_large/lama_mpe model files NOT downloaded

## Remaining Issues

1. **inpainter: none** — text residue visible under rendered text. Fix: `--inpaint-backend original` (OpenCV simple fill) or download lama models.
2. **OCR direction auto→horizontal** — vertical text rendered horizontal. Runtime issue, not fixable in mga.
3. **Memory/character profiles empty** — speaker_id not assigned by vision stage. Enhancement needed.
4. **Translation quality** — page 3 (table of contents) and page 8 (single short words) have short translations that LLM handled literally, not contextually.

## Modified Files

| File | Changes |
|---|---|
| `mga/pipeline/parsers.py` | `ast.literal_eval` fallback, `_clean_translation_text`, single-quote regex, `RATIONALE_TERM_RE` fix |
| `mga/pipeline/render_stage.py` | `_page_bubble_id()` for `region-` + `vision-` prefix matching |
| `mga/runtime_bridge/external.py` | `_run_subprocess_streamed()` with timeout + real-time output + 3 subprocess.run replacements |
| `mga/cli/main.py` | Hard fail on Pass 1 export failure (no silent fallback) |

## Test Results

- 192 pipeline + runtime tests pass, 1 xfail (pre-existing)
- 8 parser fix tests pass (Python dict repr, markdown prefix, valid JSON, plain text, single-quote regex)
- Pipeline rerun: 70 translations, 0 errors, 0 bad translations (was 6/75 before fix)
