# Recovered E2E work

This branch preserves previously uncommitted manga translation work on top of the repository default branch. It is not a release or a claim of visual E2E acceptance.

## Contents

- Eleven source files covering title/footnote rendering, vision title recovery, CLI parallel settings, provider timeouts and subprocess handling.
- Thirteen related test files and one render fixture image.
- Historical documentation under `docs/archive/recovered-e2e/`; these snapshots are not current project status. Their old local artifact links may no longer resolve.
- Sanitized configuration examples under `configs/recovered/` and `examples/recovered.env.example`. Actual environment files, credentials, experiment results, model weights, virtual environments and generated package metadata are excluded.

Hardcoded provider credentials are removed from the recovered factory and the existing default configuration example. Previously published Git history is unchanged; previously exposed credentials still require revocation by their owner.

## Known limitations

- No new paid provider calls or model-backed visual E2E validation were performed. Historical output files were intentionally discarded separately.
- The recovered translation filter excludes short ASCII alphabetic vision text, including potential dialogue such as Yes or Help. This needs review before production use.
- The recovered cover-title overlay font search uses Windows font locations and falls back to Pillow's default; CJK rendering on other platforms is not assured.
- Several recovered tests explicitly skip obsolete overlay behavior; they do not validate the current visual output.

The branch is for preservation and further review. Do not infer that all recovered heuristics should be merged unchanged.

## Validation of the recovery branch

The 13 related test files completed with **302 passed, 11 skipped, 1 xfailed**. Ten skips concern explicitly obsolete overlay behavior; one requires the optional Anthropic package. The expected failure is the existing persona-provider exception-handling case.

A full `tests/` run was interrupted after it stalled around 97%; it is not a complete passing run. That run also contained an intermediate synthetic-secret test fixture failure, subsequently corrected and verified by the final related test run.

The candidate tree was scanned for known local credential values, common API/GitHub token formats and private-key markers; no remaining matches were found. This does not certify the pre-existing remote history.
