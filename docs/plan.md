<!-- /autoplan restore point: /home/exusiai/.gstack/projects/ArmedHelicopter-manga-translator-agent/mga-layer-bootstrap-autoplan-restore-20260521-232030.md -->
# MGA Branch Completion Plan

## Goal

Ship the `mga-layer-bootstrap` branch as a merge-ready PR to `main`. The intelligence layer, two-pass runtime bridge, novel mode, benchmark/reporting tools, and host-layer tests are implemented. This file tracks the remaining local branch-prep work only; remote PR creation and merge actions are hard stops.

## Current State

As of 2026-06-04, the AFK verification branch has:

- Editable dev install passing on Windows with Python 3.12: `pip install -e ".[dev]"`.
- Full host-layer suite passing: `609 passed, 1 skipped` with `python -m pytest tests -v`.
- Console script available: `manga-translate --help` shows translate, benchmark, legacy, memory, profile, and term commands.
- `README.mga-draft.md` absent; `README.md` is the current public overview.
- Native Windows installs skip `pydensecrf`; that dependency remains available on non-Windows platforms and is only used by the legacy/runtime mask-refinement path.

## Branch Hygiene Status

| Item | Status | Evidence |
| --- | --- | --- |
| Remove stale docs | Done | `README.mga-draft.md` is not present |
| Verify install | Done | `.venv\Scripts\python.exe -m pip install -e ".[dev]"` |
| Verify tests | Done | `.venv\Scripts\python.exe -m pytest tests -v` |
| Verify CLI entrypoint | Done | `.venv\Scripts\manga-translate.exe --help` |
| Update developer guidance | Done | `CLAUDE.md` current test count |
| PR description draft | Done | `PR_DESCRIPTION.md` |

## Architecture Shipping In This Branch

```text
mga/
├── models          Pydantic v2 data models
├── config          TOML config + provider route resolution
├── format          image, PDF, EPUB, CBZ/CBR, MOBI, bilingual adapters
├── providers       LLMProvider implementations + provider cascade
├── memory          state, wiki projection, graph, profiles, evolution
├── cultural        classifier, terminology, honorific, coinage handling
├── qa              proofreaders + orchestrator
├── learning        L1-L4 learning engine
├── pipeline        7-stage pipeline, incremental, batch, two-pass manga path
├── cli             Click command surface
├── runtime_bridge  external runtime export/render integration
├── artifacts       run summaries and translation reports
├── benchmark       extraction and translation benchmarks
└── review          review/report surfaces
```

## Explicit Non-Goals

- Opening, pushing, or merging a PR from AFK mode.
- Real-world translation quality benchmarks that require paid/provider usage or manual evaluation.
- Native Windows `pydensecrf` runtime support without local C++ Build Tools.
- Production deploys, releases, tags, or public announcements.

## Local PR Prep

- Use `PR_DESCRIPTION.md` as the draft PR body.
- Keep commits on an AFK branch/worktree until the user explicitly chooses commit organization and any remote action.
- Before any final commit or PR, rerun `pip install -e ".[dev]"`, `pytest tests -v`, and `manga-translate --help` in a Python 3.10-3.12 environment.
