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

<!-- none yet -->
