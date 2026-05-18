# Manga Translate Agent

`mga` 不是另一个 OCR/MT wrapper。

它当前的产品定义是一个 **external-first 的漫画翻译 Agent**：以 `manga-image-translator` 这类成熟 runtime 为底盘，以 `mga` 自己的 artifacts、benchmark、review、角色一致性 intelligence 为上层。

短期内，`mga` 借用成熟 external runtime 解决“能跑、能看、能对比”的交付问题；长期则把护城河建立在角色一致性翻译、关系约束生成、`learn-from` 和 QA 审查上。

当前仓库已经进入 **external-core** 重构阶段：默认翻译主链走受控 external runtime，`mga` 负责 orchestration、artifacts、benchmark、review 与后续 intelligence 层。

## External-First 架构

`mga` 当前按三层来理解：

- **external runtime core**：检测、OCR、擦字、嵌字、页级翻译底盘
- **mga orchestration layer**：artifacts、benchmark、review、provider routing、run control
- **mga intelligence layer**：角色一致性翻译、`learn-from`、QA、关系约束

对应的长期记忆方案采用 `project-scoped memory wiki layer`：`memory/state/` 是 runtime canonical source，`memory/characters|scenes|terms|decisions|indexes/` 是 human-readable wiki projection；repo `docs/` 只保留 ADR、模板、规范和示例。

这意味着近期推荐路径不是“完全替代 external runtime”，而是：

- 用 `external` 作为短期交付主链路
- 停止把 `internal structured pipeline` 作为产品实现主线
- 逐步把 `mga` 的 translation brain、QA 与长期记忆能力插到 external runtime 上

## 它和传统项目的区别

- **句子翻译 vs 角色发言生成**：传统系统翻译单句，`mga` 试图生成“这个角色在这个关系与情绪场景下会怎么说”
- **runtime commodity vs intelligence proprietary**：成熟 runtime 可以复用，但角色一致性、关系约束和 QA 审查是 `mga` 自己的核心资产
- **OCR-first vs scene-aware vision-first**：传统 pipeline 先把图像降维成文本，`mga` 则把画面与结构化 artifacts 保留下来，作为上层生成与审查的基础
- **术语库 vs 人格校准**：传统系统主要统一词汇，`mga` 还要学习角色在中文中的人格质感
- **纠错 QA vs 人设一致性 QA**：`mga` 的 QA 不只查错，还查角色是否说得像自己

## Phase 1 能力

- **图片目录 MVP**：只支持本地图片目录输入与图片输出
- **External-core 主链路**：`translate` 默认调用 external runtime 并统一落盘 artifacts
- **Legacy benchmark 保留**：`benchmark-external` 继续负责外部对比，legacy extraction 研究命令继续保留
- **可审查 artifacts**：每次运行都会落盘 `manifest.json`、`external-baseline-summary.json`、`external-baseline-text*.json/txt`、`run.json`
- **单 provider 路径**：Phase 1 只支持一条 OpenAI 云端 provider 路径
- **基础嵌字**：优先保证可读和可排障，不追求最终专业排版

## 项目结构

```text
manga-translate-agent/
├── configs/
│   └── providers.toml.example
├── docs/
├── pyproject.toml
├── README.md
├── src/
│   └── manga_translate/
│       ├── __init__.py
│       ├── cli.py
│       ├── exceptions.py
│       ├── artifacts/
│       ├── benchmark/
│       ├── config/
│       ├── format/
│       ├── legacy/
│       ├── models/
│       └── runtime/
└── tests/
    ├── e2e/
    ├── fixtures/
    ├── integration/
    └── unit/
```

## 快速开始

```bash
# 安装
pip install -e ".[vision,dev]"

# 配置供应商
cp configs/providers.toml.example configs/providers.toml
# 编辑 configs/providers.toml 填入 API key

# 翻译图片目录（默认 external-core）
manga-translate input/ -o output/
```

如果要跑对比与研究命令，可继续使用 `benchmark-external`、`legacy benchmark-extraction` 和批处理 review 脚本。

## 输出目录

一次运行会生成：

```text
output/
├── manifest.json
├── external-baseline-summary.json
├── external-baseline-text.txt
├── external-baseline-text-normalized.json
└── run.json
```

## 当前限制

- 只支持图片目录输入
- 只支持 `ja-zh`
- 只支持 `--format images`
- `--local`、`--learn-from`、per-stage provider override 暂未实现
- `translate` 当前固定走 external-core，不支持 `--dry-run`
- OCR / structured extraction 研究命令已降级到 `legacy`
- legacy extraction 对比仍可使用，但不属于当前产品主路径

## Legacy 研究命令

如果你要继续验证旧的 vision-first / OCR 提取研究链路，请使用：

```bash
PYTHONPATH=src python -m manga_translate.cli legacy benchmark-extraction data/sources/real_pages/test -o data/runs/benchmark/legacy_benchmark --sample-size 5 --sample-start 0
```

它会在同一批页面上同时产出：

- `benchmark/vision/*.json`：Vision-first 提取结果
- `benchmark/ocr/<spec>/*.txt`：多 OCR 配置原始结果
- `benchmark/extraction-report.json`：提取对比报告
- `benchmark/translation-report.json`：翻译对比报告
- `benchmark/annotations.extraction.template.json`：提取基准人工标注模板
- `benchmark/annotations.translation.template.json`：翻译基准人工标注模板
- `benchmark/run.json`：本次 benchmark 的参数、状态、失败原因与产物索引

正式 external runtime 对比命令：

```bash
PYTHONPATH=src python -m manga_translate.cli benchmark-external \
  data/sources/real_pages/test \
  -o data/runs/external/smoke_external \
  --repo-dir external/external/manga-image-translator
```

这条命令会把 external runtime 结果归一化到 `mga` 的 benchmark/report 体系，会额外生成：

- `external-baseline-summary.json`
- `external-baseline-text.txt`
- `external-baseline-text-normalized.json`
- `benchmark/external-translation-report.json`

legacy extraction 统一对比仍仅用于研究，不属于当前默认交付路径。

如果你想一次准备连续页样本、跑 internal/external、再组装 review 目录，可以使用：

```bash
bash scripts/run_external_review_batch.sh
```

这个脚本当前支持：

- provider preflight
- `SKIP_INTERNAL=1` / `SKIP_EXTERNAL=1`
- 心跳式进度日志
- review 目录自动组装

当前 OCR 基线默认包括：

- `tesseract_jpn`
- `tesseract_jpn_vert`
- `tesseract_jpn+eng`

支持两种抽样策略：

- `--sample-strategy window --sample-start 20 --sample-size 8`
- `--sample-strategy random --sample-size 8 --sample-seed 42`

如果你补好人工标注，可以继续跑带评分版本：

```bash
PYTHONPATH=src python -m manga_translate.cli legacy benchmark-extraction \
  data/sources/real_pages/test \
  -o data/runs/benchmark/legacy_benchmark \
  --sample-size 5 \
  --annotations data/runs/benchmark/direct_test/benchmark/annotations.gold.json
```

## 文档

| 文档 | 内容 |
|------|------|
| [PRD](docs/PRD.md) | 产品需求：用户、功能、路线图、竞品 |
| [SPEC](docs/SPEC.md) | 技术设计：架构、数据结构、提示词、供应商 |
| [开源调研](docs/research/oss-landscape.md) | GitHub 开源项目生态分析 |
| [闭源调研](docs/research/market-landscape.md) | 闭源产品与市场分析 |

## 路线图

| Phase | 内容 | 状态 |
|-------|------|------|
| 1 | 图片目录 MVP：建立基础 artifacts 与 legacy 研究合同 | ✅ |
| 1.5 | external-core 交付链路：把 `manga-image-translator` 固定为默认 runtime / core | 🚧 |
| 2 | external runtime 魔改：把 `mga` 的 prompt-orchestrated generation 插到 external runtime 上 | ⬜ |
| 3 | 人格校准：`--learn-from` 作为角色语言热启动入口 | ⬜ |
| 4 | 关系约束与角色一致性 QA：把角色系统升级为正式 intelligence layer | ⬜ |
| 5 | 更多格式与 provider 路径 | ⬜ |
| 6 | 对 external runtime 的更深改造与审计强化 | ⬜ |

## 发布纪律

- 任何 commit/tag 前必须确认本地 secret 未被追踪
- `configs/providers.toml`、本地 venv、`data/`、`external/`、benchmark/debug/review 输出必须保持忽略
- external vendor repo 不得混入版本库
- benchmark/debug artifacts 只保留需要长期引用的文档资产，不提交大体积运行产物
