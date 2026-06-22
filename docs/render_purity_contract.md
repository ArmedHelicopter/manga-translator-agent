# Render Purity Contract

**Goal:** The rendered output of any page `P_n` is a deterministic function of **only** the input image `I_n` and that page's translation `T_n` — `render(P_n) = f(I_n, T_n)` — with no dependence on other pages, run history, caches, or non-determinism.

## PRD constraints (binding)

This contract is pursued **within** the project PRD (`docs/PRD.md`); it does not override it:

- **§4.1 / §4.2.1 — runtime artifact is authoritative geometry.** OCR/runtime provides `source_text` and `bbox`; the runtime artifact (`artifact-NNNN.json` text_regions) is the authoritative source of text and geometry. `mga` does **not** re-derive, re-run, or override OCR geometry. Vision does not override OCR text (§3.1).
- **External-first (§1.2.2).** Detection / OCR / inpaint / render are the runtime's job (commodity). `mga` owns intelligence, artifacts, review.
- **Edit scope.** `mga/` remains the primary edit surface, but the runtime is **not** a black box — modifying the local runtime `manga_translator/` is **allowed**. When a real runtime bug blocks delivery (e.g. footnote-font hardcoding → Windows tofu), prefer an mga-side fix when feasible; otherwise patch `manga_translator/` (the copy mga invokes via `python -m manga_translator` with `cwd=project_root`).

Therefore the render **cannot** be made independent of the artifact — the artifact *is* the geometry of `I_n`. Purity is achieved by treating the artifact as the **pinned, authoritative** `g(I_n)` and making `mga`'s own contribution a pure function of `(I_n, T_n, artifact)`.

## Purity model

```
render(P_n) = RenderStep( I_n ,  T_n ,  artifact_n )
                                  │
                                  └─ artifact_n = g(I_n)   ← authoritative runtime geometry (PRD), pinned in the payload

 ⇒  for a fixed payload,  render(P_n) = f(I_n, T_n)
```

The `mga` render layer (`mga/pipeline/render_stage.py`) guarantees:

1. **No persistent state.** The S2T converter memo is instance-scoped (`self._s2t_converter_cache`), not class-level. A freshly constructed `RenderStage` carries no inherited mutable state, so output never depends on process history or prior runs.
2. **Per-page isolation.** `_write_page_translations(page_idx)` consumes only translations whose `bubble_id` matches `region-{page_idx:04d}-` and only the matching `Page` object. Page `n`'s output is independent of page `m`'s translations, pages, or state.
3. **Determinism.** Given `(I_n, T_n, artifact_n)`, the written `translations-NNNN.json` is byte-identical across separate `RenderStage` instances.
4. **`I_n`-faithful render decisions (anti-hallucination, PRD §3.1 P1).** The OCR hallucination guard drops translations whose OCR region lands on a blank area of `I_n`. This is a *render decision* (what to render), not a geometry override — it does not alter the authoritative artifact. It makes the output respect `I_n`'s actual content.

## Image-level reproducibility (proven)

The rendered **image** — not just the intermediate JSON — is reproducible. Two kinds of real-runtime evidence:

1. **Same pinned payload, rendered twice** → all 10 output pages were byte-identical (sha256 match). The render-only function is deterministic in its full output given pinned `(I_n, T_n, artifact)`.
2. **Cross-render with a CHANGED artifact** (the `g(I_n)` determinism test): page-005 was rendered three times against the real runtime —
   - R1: real artifact v1, pin ON
   - R2: artifact v2 (region 0 moved), pin ON → pin restored v1
   - R3: artifact v2, pin OFF

   Result: `sha256(R1) == sha256(R2)` (the pin neutralized the artifact change) and `sha256(R1) != sha256(R3)` (without the pin, the change propagates). So with pinning on (the default), the rendered image is invariant to OCR-artifact changes — `g(I_n)` is pinned and `render(P_n) = f(I_n, T_n)` holds across runs at the real image level.

## Closing the `g(I_n)` gap: content-addressed artifact pinning

The one remaining source of cross-run variance is the runtime OCR that produces `artifact_n = g(I_n)` — it is not strictly deterministic across fresh Pass-1 runs (e.g. page-010 region-count variance). The runtime cannot be made deterministic from `mga` (PRD: runtime is authoritative commodity). Runtime edits are permitted (see Edit scope above), but determinism is achieved less invasively by pinning the artifact spine than by patching the runtime's OCR.

`mga` closes this gap at the **artifact spine** (PRD §4.1) with content-addressed pinning (`mga/runtime_bridge/artifact_cache.py`):

- `image_sha256(I_n)` identifies the input image by its bytes.
- `ArtifactPin` stores the first-seen OCR artifact keyed by `sha256(I_n)` in a **persistent, project-scoped** store (`<working_dir>/.mga_cache/artifact-pin.json`), so the pin survives across pipeline invocations — not just within one payload.
- On render, `resolve_pinned_artifact` restores the pinned artifact for `I_n` before the guard and subprocess run — so a fresh re-OCR that overwrites the artifact does **not** change the rendered output.

`pin_artifacts` **defaults to `True`** — reproducibility is the product goal, so the default render is a deterministic function of `(I_n, T_n)`. With pinning on, `g(I_n)` is a deterministic (constant) function of `I_n` for the lifetime of the pin store, so the **end-to-end rendered image is a deterministic function of `(I_n, T_n)`** even across runs. Set `pin_artifacts=False` to always use the fresh Pass-1 artifact (non-deterministic, but picks up OCR changes); delete the pin sidecar to force a re-pin.

## Verification

`tests/pipeline/test_render_stage_ocr_guard.py::TestRenderPurity` and `tests/runtime_bridge/test_artifact_cache.py` prove the guarantees:

| Test | Property |
|------|----------|
| `test_output_deterministic_across_instances` | Same `(I_n, T_n, artifact)` → byte-identical output across fresh instances |
| `test_output_independent_of_other_pages` | Page `n` output unaffected by page `m`'s presence (isolation) |
| `test_output_depends_on_translation` | Different `T_n` → different output (non-trivial in `T_n`) |
| `test_output_depends_on_input_image` | Same artifact+`T_n`, different `I_n` → different output (guard respects `I_n`) |
| `test_no_class_level_mutable_state` | No class-level mutable cache leaks across instances |
| `test_pinning_makes_artifact_deterministic_across_reruns` | With `pin_artifacts=True`, a re-OCR overwriting the artifact does not change output (`g(I_n)` pinned) |
| `test_artifact_cache.py::*` (9 tests) | `image_sha256` determinism, `ArtifactPin` get/put/persistence, `resolve_pinned_artifact` first-seen-wins + restore |
