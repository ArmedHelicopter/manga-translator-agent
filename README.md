# Manga Translate Agent

**已停止维护。** 大一实验结题存档，不是产品。

`mga` is an external-first host layer on [zyddnys/manga-image-translator](https://github.com/zyddnys/manga-image-translator). OCR、inpaint、lettering 仍在 runtime 里。

相对 manga-image-translator 和 [BallonsTranslator](https://github.com/dmMaze/BallonsTranslator)，这个实验想补的是跨页角色记忆、QA、cultural notes，不是更好的排字。

## 实际交出来的

- 两遍 runtime bridge：Pass 1 导出 `artifact-NNNN.json` / `inpainted-NNNN.png`，host 翻译，Pass 2 回填渲染。合同见 [`docs/render_purity_contract.md`](docs/render_purity_contract.md)。
- `mga/memory/`、`mga/qa/`、`mga/cultural/` 模块存在，有集成测试。
- 10 页 fixture 做过视觉审图。证据名和日期在 [`docs/STATUS.md`](docs/STATUS.md)。

角色一致性是 headline，成熟度停在 L2，不是 L3。不要当已上线能力卖。

## 没做成的

事实文件是 [`docs/STATUS.md`](docs/STATUS.md)（Last verified: 2026-06-28）：

- OCR accuracy: 目标 > 98%，实测 47%（47/100 regions）
- Per-page time: 目标 < 30s，实测 ~244s
- Character consistency: L2，不是 L3 vision-e2e
- Learning engine: 模块 + mock tests；real hot-start loop unverified
- Translation parallel speedup: **UNVERIFIED**

[`docs/SPEC.md`](docs/SPEC.md)、[`docs/PRD.md`](docs/PRD.md)、[`docs/ROADMAP.md`](docs/ROADMAP.md) 是历史文档，过时。

## 仓库怎么读

- 产品代码在分支 `afk-gpt-5`（本 README 所在分支）。
- 这个 GitHub fork 的 `main` 跟踪上游 manga-image-translator。不要把 `main` 当产品。
- 包结构：`mga/` 是 host；`manga_translator/` 是 vendored runtime 副本。许可证 GPL-3.0。

## 最短可跑命令

```bash
pip install -e ".[dev]"
manga-translate --help
```

这只确认 CLI 装上了。它不证明翻译质量，也不是生产路径。

## 不要 fork 这个仓当产品

要漫画翻译，用上游 manga-image-translator 或 BallonsTranslator。

要看这次 host-layer 实验，读 [`docs/WRAPUP.md`](docs/WRAPUP.md) 和 [`docs/STATUS.md`](docs/STATUS.md)。气泡裁切在 [`docs/demo/`](docs/demo/)。
