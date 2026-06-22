# End-to-End (E2E) Testing

## What the e2e test is

The e2e test runs the **full manga translation pipeline** on a representative sample and inspects the **actually rendered images** — not just intermediate JSON or unit tests.

Pipeline stages (in order): `format → ocr_artifact → ocr_guard → vision → speaker_attribution → character → character_memory → translation → qa → render`.

- **Input**: a small representative image set — `data/input/e2e-3pages/` (cover + table-of-contents + content page; deliberately exercises font / footnote / vertical-text edge cases).
- **Runtime**: external-two-pass, render-only mode. mga invokes the worktree-local `manga_translator/` via `python -m manga_translator` with `cwd=project_root`.
- **Provider**: mimo (vision `mimo-v2.5`, translation/qa `mimo-v2.5-pro`) — see `configs/providers.toml`.
- **Output**: rendered `page-*.png`, `translations/page_*.json`, `manifest.json`, `run.json`, `qa_report.json`, and `.mga-payload/` intermediates.

The e2e test is the **ground truth** for whether a change actually fixes a rendering/translation defect. Unit tests can be green while the rendered images are still broken — this has happened (the markdown-leak + footnote-tofu regression shipped with a green suite).

## How to run it

```powershell
cd C:\Users\Administrator\.paseo\worktrees\manual-afk-gpt-5-manga-translator-agent-local-head
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"

# Force a FRESH run (do not let stale cache / pinned artifacts mask the fix):
#   - move .mga_cache\llm_cache.db aside (or clear the relevant entries), and
#   - delete .mga_cache\artifact-pin.json
.\.venv\Scripts\manga-translate.exe data/input/e2e-3pages/ -o data/output/e2e-full-fresh
```

Always run into a **new output dir** when validating a fix, so you compare against freshly rendered images rather than a stale directory.

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
