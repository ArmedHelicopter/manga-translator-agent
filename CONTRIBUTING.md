# Contributing

## Never commit runtime model weights

`models/`, `*.ckpt`, and any runtime weight (translation vocabs, spm models) must **never** enter git history. `.gitignore` enforces this, but the rule is the root cause — gitignore is defense, not permission.

- Weights are large, binary, and versioned by the upstream runtime (manga-image-translator), not by this repo. Committing them bloats history (a past incident added 1.22 GB), trips GitHub's 100 MB limit, and makes every clone expensive.
- Avoid `git add -A` / `git add .` — a WIP snapshot once swept in the whole `models/` tree. Stage files explicitly.

## Before pushing a branch with long local history

Scan for big blobs so GitHub doesn't reject the push after a multi-minute upload:

```bash
git rev-list --objects --all | awk '{print $1}' | sort -u | \
  git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' | \
  awk '$1=="blob" && $2>104857600 {print "BIG:", $2, $3}'
```

## If a fresh clone lacks `models/`

Restore the weights from an external copy (they live outside git):

```bash
# Windows symlink (needs developer mode or admin):
cmd //c "mklink /D models E:\path\to\manga-image-translator\models"
# or copy:
robocopy "E:\path\to\manga-image-translator\models" models /E
```

## Modifying the local runtime (`manga_translator/`)

The vendored runtime under `manga_translator/` is what mga invokes. Patching it is permitted only when a real runtime bug blocks delivery and an mga-side fix isn't feasible (see `docs/render_purity_contract.md`, PRD §1.2.2). Record every such patch in `docs/runtime-patches.md` so runtime changes stay visible and reviewable.

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```
