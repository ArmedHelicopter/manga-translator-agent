# History Rewrite — strip runtime model weights (2026-06-22)

> Why `afk-gpt-5`'s history was rewritten, what was removed, and how `models/` is managed now.
> Read this before committing anything under `models/` or any `*.ckpt` — it exists to stop the
> same >100MB-blocks-push failure from recurring.

## What happened

Pushing `afk-gpt-5` to origin was rejected by GitHub:

```
remote: error: File models/detection/detect-20241225.ckpt is 294.09 MB; exceeds GitHub's 100 MB limit
remote: error: File models/inpainting/lama_large_512px.ckpt is 195.07 MB; ...
remote: error: File models/ocr/ocr_ar_48px.ckpt is 194.83 MB; ...
```

All three (plus the rest of `models/` — translation vocabs, spm models, etc.) entered history in
one shot via commit `83d5ef6` "wip: mga-layer-bootstrap WIP snapshot", which committed the entire
`models/` runtime-weight directory. `.gitignore` did not cover `*.ckpt` or top-level `models/`
(only `data/models/` and `*.bin/*.pt/*.onnx`), so nothing stopped it. Repo object store had grown
to **1.22 GiB**.

## Fix

1. `git filter-repo --path models --invert-paths` on an **isolated clone** (NOT the shared
   worktree `.git`) — stripped `models/` from all 2099 commits. Code content unchanged; only
   `models/` paths removed, every hash rewritten.
2. `.gitignore` gained `*.ckpt` and `/models` (top-level runtime model dir + the symlink).
3. Pushed clean history (first push of `afk-gpt-5` — no force needed, branch didn't exist remote-side).
4. The other worktree agent had one unpushed commit (`01b9f19`, dict-repr fix) on the old history.
   **Crucial**: it was NOT in the rewritten remote (the filter-repo clone was taken before that
   commit existed). It was **cherry-picked** onto the new history (`b83a545b`) rather than lost.
5. `models/` restored as a **symlink** → main repo's `models/` (external, untracked).

## Why a symlink, not committed weights

Runtime model weights (`.ckpt`, translation vocabs/spm) are large, binary, and versioned by the
upstream runtime (manga-image-translator), not by this repo. Committing them bloats history
(1.22 GB here), trips GitHub's 100 MB limit, and makes every clone expensive. They belong
**outside git**, restored per-machine. The symlink points at the main repo's copy so multiple
worktrees share one set of weights.

## Lessons (for agents and humans)

- **Never commit `models/`, `*.ckpt`, or any runtime weight.** `.gitignore` now enforces this,
  but the *rule* is the root cause — gitignore is defense, not permission. A WIP `git add -A` on
  a dirty tree bypassed it once; don't repeat.
- **Before pushing a branch with long local history, scan for big blobs** so GitHub doesn't
  reject it after a multi-minute upload:
  ```
  git rev-list --objects --all | awk '{print $1}' | sort -u | \
    git cat-file --batch-check='%(objecttype) %(objectsize) %(rest)' | \
    awk '$1=="blob" && $2>104857600 {print "BIG:", $2, $3}'
  ```
- **WIP snapshot commits are dangerous** — `83d5ef6` swept in the whole `models/` tree. Avoid
  `git add -A` / `git add .`; stage explicitly.
- **History rewrite + shared worktree**: run `filter-repo` on an isolated clone, not the shared
  `.git`, so other agents' in-flight work is untouched. Then cherry-pick any unpushed commits
  back (they won't be in the rewritten remote).

## If a fresh clone lacks `models/`

```
# Windows symlink (needs developer mode or admin):
cmd //c "mklink /D models E:\path\to\manga-image-translator\models"
# or copy:
robocopy "E:\path\to\manga-image-translator\models" models /E
```
