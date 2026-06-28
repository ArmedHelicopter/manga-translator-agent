# Archived Documentation

Point-in-time process artifacts — handoff notes, overnight progress logs, delivery/status snapshots, completed plans, dated code reviews, and resolved-bug writeups. Kept for historical reference but **not** maintained. For the current state of the system, see the living docs under `docs/` (start with `STATUS.md`).

Load-bearing information that was salvaged before archiving:

| Salvaged content | Now lives in |
|---|---|
| 4 known runtime limitations (inpainter none, OCR direction, font_size, empty memory) | `docs/runtime-patches.md` § Known Runtime Limitations |
| Detection parameter tuning table | `docs/detection-tuning.md` |
| Never-commit-weights rule, big-blob pre-push scan, models/ restore | `CONTRIBUTING.md` |
| Service-layer architecture (MemoryService/CulturalService/PromptBuilder) | `CLAUDE.md` (already current) |

Note: `plan-root-local.md` is an older local-only copy (untracked) of the branch-completion plan; the tracked superset is `plan.md` in this directory.
