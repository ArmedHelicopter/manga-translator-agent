# 结题备忘（写给一年后的自己）

2026-08-31。大一实验停在这里。不要当还在维护的产品读。

## 为什么停

精力被 runtime 排字吃掉了。font-shrink、dst_points、空白页 payload 槽、footnote 字体，这些都是 `manga_translator/` 里的活。

Headline 是跨页角色一致性。STATUS 标的是 L2：memory 非空、updater 能写 profile。它没有到 L3（rendered PNG 上的 vision-e2e）。继续堆 lettering 也填不上这个缺口。

OCR 47% vs 目标 >98%，约 244s/页 vs 目标 <30s。平行加速是 UNVERIFIED。数字在 `docs/STATUS.md`，结题后不再刷。

## 分支

- 本地 `afk-gpt-5-main`、origin `afk-gpt-5`：产品代码。本 README 在这条线上。
- origin `main`：上游 manga-image-translator 镜像。不是产品。
- 不要 unfork。还要留一个小的上游 PR 通道。

读 GitHub 时先确认分支。fork 的 `main` 看起来像 manga-image-translator，那是对的。

## 值得记住的 runtime 补丁

清单在 `docs/runtime-patches.md`。真有用的两处：

- 2026-06-22 font-shrink loop：`manga_translator/rendering/__init__.py`。译文比原文长时，上游会拿 oversized `temp_box` 做透视，字溢出气泡。
- 2026-06-27 keep `dst_points = region.min_rect`：fit 完之后不要再扩 target polygon。page-007 左下竖排就是这么漏出去的。

不要当上游补丁推的：Pass 1 在 mask 前按 OCR `prob < 0.25` 过滤。那是 mga 两遍管线特有的（host 的 render guard 和 runtime erase 必须对齐）。单跑上游时这套阈值没有对应物。

## E2E 证据在哪

`data/output/` 被 gitignore。当前 worktree 里这个目录不存在。STATUS 里的名字：

- `recon-fresh-20260624-v4`
- `e2e-overflow-fix-20260627-v5`
- `e2e-render-current-20260628-footnotes-on-v2`

本机完整页在另一个 worktree：`C:\Users\Administrator\.paseo\worktrees\manual-afk-gpt-5-manga-translator-agent-local-head\data\output\`（`e2e-overflow-fix-20260627-v10-current-code-from-original-v4`、`e2e-render-current-20260628-footnotes-on-v2`）。当前仓 `data/output/` 不存在。

公开 git 只放了三张气泡/页脚裁切，见 `docs/demo/`。不要为了结题再跑一遍 10 页 e2e。

## 以后若要捡起来

把 `mga/` 抽成新仓库，把 manga-image-translator 当依赖调用。不要继续在这个 fork 上长。

GPL-3.0 跟着 runtime 副本走。抽的时候先把许可证理清。

## 版权

永远不要 commit `data/input/` 里的 PDF 或完整漫画页。测试图、扫描件、第三方下载都不进 git。
