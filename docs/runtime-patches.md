# Runtime Patches

Log of patches made to the **local runtime `manga_translator/`** — the copy mga invokes via `python -m manga_translator` with `cwd=project_root`. It is worktree-local, so patches here stay in this worktree (tracked by git like any other code). Optional: use this to capture rationale that a commit message alone wouldn't.

Per the Edit scope (`docs/render_purity_contract.md`; PRD §1.2.2), modifying the local runtime `manga_translator/` is permitted when a real runtime bug blocks delivery and an mga-side fix is not feasible. Record each patch here so runtime changes are visible and reviewable.

## Format

```
### YYYY-MM-DD — <short title>
- **File**: `manga_translator/<path>:<line>`
- **Upstream behavior**: <what the runtime did wrong>
- **Patch**: <what was changed>
- **Why not mga-side**: <why an mga-side fix wasn't feasible>
- **Verified by**: <how the fix was confirmed against rendered output>
```

## Entries

### 2026-06-22 — Footnote font chain (CJK tofu fix)
- **File**: `manga_translator/manga_translator.py:754-807` (`_draw_footnotes`)
- **Upstream behavior**: The footnote rendering code used a Linux-only font path (`/usr/share/fonts/...NotoSansCJK...`) and fell back to `ImageFont.load_default()` when that path didn't exist. On Windows, `load_default()` returns a bitmap font with no CJK coverage, so all footnote text (katakana loanwords, cultural terms, coined words) rendered as tofu boxes (□□□).
- **Patch**: Replaced the single Linux path with a cross-platform font chain that tries, in order: repo-bundled `fonts/msyh.ttc`, `fonts/Arial-Unicode-Regular.ttf`, `fonts/msgothic.ttc`, then Windows system fonts (`C:/Windows/Fonts/msyh.ttc`, `C:/Windows/Fonts/msyhbd.ttc`), then Linux Noto paths, and only falls back to `load_default()` as a last resort. All three repo-bundled fonts and both Windows system fonts are confirmed present on this machine.
- **Why not mga-side**: The footnote text is rendered directly onto the image by the runtime's `_draw_footnotes` method using PIL. mga passes footnote data as JSON metadata, but the actual glyph rendering happens inside the runtime subprocess. No amount of mga-side data cleaning can fix missing font glyphs — the font must be available at render time.
- **Verified by**: Render stage re-run with cleaned translations; vision verification of rendered PNGs confirms footnote text is readable CJK (not tofu).

### 2026-06-22 — Runtime resolution: top-level vendored copy is what runs
- **Finding**: `mga/runtime_bridge/external.py::run_export_artifact` (lines 601-607) and `run_render_only` (lines 725-729) prefer `project_root / "manga_translator" / "__main__.py"` when it exists. The worktree has a top-level `manga_translator/` directory (regular directory, NOT a junction) that takes precedence over `external/manga-image-translator/` (which IS a junction to the shared main repo). Therefore, the footnote font fix must be applied to the top-level copy, not the external/ copy. The `external/` copy has NO footnote code and editing it would have no effect. This was confirmed by: (1) code analysis of the resolution logic, (2) `fsutil reparsepoint query` showing the top-level copy is a regular directory, (3) grep confirming `_draw_footnotes` exists only in the top-level copy.
- **Implication**: When patching the runtime, always check which copy actually runs. The top-level `manga_translator/` is worktree-local and safe to edit. The `external/` copy is shared via junction and patches there affect the main repo (log them here if made).

### 2026-06-22 — Font-shrink loop for overflowing vertical/horizontal text bubbles
- **File**: `manga_translator/rendering/__init__.py:458-520` (`render` function, font-shrink loop)
- **Upstream behavior**: When translated text is longer than the original (e.g. a 34-character Chinese sentence in a narrow vertical bubble that originally held 3 lines of Japanese), `calc_vertical` wraps the text into multiple columns. The resulting `temp_box` is wider than the bubble. The `render` function then tries to match the box ratio to the bubble ratio via padding (`h_ext` / `w_ext`). When the text is so long that padding goes negative, `render` falls back to `box = temp_box.copy()` — using the oversized box as-is. The perspective warp then maps this oversized box onto the bubble's `dst_points`, causing text to overflow the bubble boundary (visible as text extending past the right edge of the bubble in page-003's top-right region).
- **Patch**: Added a font-shrink loop between text rendering and box padding. When the rendered `temp_box` has a worse aspect ratio than the bubble (`r_temp > r_orig` for vertical, `r_temp < r_orig` for horizontal), the loop reduces `font_size` by 10% per iteration (down to 40% of the original) and re-renders. This gives `calc_vertical` / `calc_horizontal` fewer characters per column/line, producing a narrower `temp_box` that fits within the bubble. The loop runs at most 20 iterations. Without this fix, long translated text in narrow bubbles overflows the bubble boundary — the text spills out past the edge and is visually broken. With the fix, the font auto-shrinks until the text fits, and the perspective warp maps it cleanly within the bubble.
- **Why not mga-side**: The overflow happens inside the runtime's `render` function during perspective warping. mga has no control over how the runtime sizes and warps text boxes — it only passes translation text and footnote metadata. The font-shrink loop must be inside `render` where `temp_box` dimensions are known.
- **Verified by**: Rendered page-003 via RenderStage with the fix. Vision model (mimo-v2-omni) confirmed: "All text stays entirely within the bubble boundary; there is no overflow to the right or any other edge. The text is sharp, fully legible." Before the fix, the same bubble showed text overflowing past the right edge.
