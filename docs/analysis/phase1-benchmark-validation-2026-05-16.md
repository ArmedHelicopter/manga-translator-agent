# Phase 1 Benchmark 验证纪要

日期：2026-05-16

## 背景

这是一份 Phase 1 的阶段性 benchmark 验证纪要，不是最终论文式评测，也不是对外宣传稿。目标是把当前已经可复现的证据、已成立的结论、仍未解决的问题，固化成一页可引用的工程记录。

当前验证重点是两件事：

- `vision-first` 主链路是否已经明显优于 OCR 基线，至少足以支撑 Phase 1 的技术方向。
- `structured` 与 `direct` 两种翻译模式是否都能产出可用结果，以及它们当前的差异和限制是什么。

## 数据与方法

本轮纪要使用了三组现有证据：

1. 本轮重新验证后完整跑通的 2 份 smoke benchmark
   - `data/runs/benchmark/smoke1/benchmark/*`
   - `data/runs/benchmark/smoke1_p1/benchmark/*`
2. 之前已有的 2 页 extraction 量化报告
   - `data/runs/benchmark/direct_scored/benchmark/extraction-report.json`
3. 尚未完成的 5 页批量验证运行状态
   - `data/runs/benchmark/split_test/benchmark/run.json`

比较对象分成两类任务，必须严格区分：

- `extraction-report`
  - 用于比较“日文源文本抽取”能力。
  - 这里比较的是 `vision_structured`、OCR 基线，以及历史报告中用于对照的 `vision_direct`。
- `translation-report`
  - 用于比较“中文翻译输出”能力。
  - 这里比较的是 `structured` 与 `direct` 两种翻译模式。

当前 OCR 基线包括：

- `tesseract_jpn`
- `tesseract_jpn_vert`
- `tesseract_jpn+eng`

## 核心发现

### 1. Extraction：`vision_structured` 已经明显优于 OCR 基线

基于 `data/runs/benchmark/direct_scored/benchmark/extraction-report.json` 的 2 页量化结果，当前平均估计字符错误率如下：

- `vision_structured`: `0.0054`
- `tesseract_jpn_vert`: `0.3863`
- `vision_direct`: `0.8223`
- `tesseract_jpn`: `0.9447`
- `tesseract_jpn+eng`: `0.9714`

当前可支持的阶段性判断：

- `vision_structured` 是当前 Phase 1 最强、最稳定的 extraction 主链路。
- `tesseract_jpn_vert` 是唯一还有比较价值的 OCR 基线，但依然明显落后于 `vision_structured`。
- `tesseract_jpn` 与 `tesseract_jpn+eng` 基本不可作为主力 extraction 方案。
- `vision_direct` 不适合作为 extraction 主链路，它的输出目标本来更接近“直接翻译”，不是“日文源文本抽取”。

这也意味着：当前阶段继续押注 `vision-first + structured page JSON` 是合理的。

### 2. Translation：`structured` 与 `direct` 都可用，但 `direct` 波动更大

本轮 smoke 结果来自两次完整跑通的 1 页验证：

- 第 1 页：`data/runs/benchmark/smoke1/benchmark/translation-report.json`
- 第 2 页：`data/runs/benchmark/smoke1_p1/benchmark/translation-report.json`

当前 translation 侧不做伪量化结论，只做质性观察：

- 第 1 页里，`structured` 明显优于 `direct`
  - `structured`: `第32话 / 这就是爱着人类、怜惜人类、信任人类之人的末路啊。 / 妖狐`
  - `direct`: `第32话 / 这就是 / 爱人、怜人、 / 信人者的末路 / 化狐`
  - 观察：`direct` 在这一页里出现了更强的压缩、误译和词汇退化，例如 `妖狐 -> 化狐`。
- 第 2 页里，两者都可读，但风格与信息保留方式不同
  - `structured`: `就算见到这样的我 / 你还打算继续站在人类那边吗？ / ……我和你不一样 / 不，并没有不同`
  - `direct`: `你还要继续站在人类那边吗？ / 还要看着这样的我吗？ / ……我和你不一样。 / 不，你错了。`
  - 观察：`direct` 在这一页的流畅度不差，但与 `structured` 相比，句序、语气、逻辑关系都有更明显的自由改写。

当前可支持的阶段性判断：

- `structured` 与 `direct` 两条翻译链路都已经能产出完整结果。
- 但 `direct` 当前质量波动更大，不宜替代 `structured` 成为默认主链路。
- `direct` 更适合作为可选模式或对照模式，而不是当前的默认推荐方案。
- external baseline 现已纳入 translation 对比链路，但当前仍以页级 `joined_text` 为主，不进入 extraction 统一评估。

## 证据清单

本纪要对应的关键 artifact 如下：

- Smoke benchmark，第 1 页
  - `data/runs/benchmark/smoke1/benchmark/run.json`
  - `data/runs/benchmark/smoke1/benchmark/extraction-report.json`
  - `data/runs/benchmark/smoke1/benchmark/translation-report.json`
- Smoke benchmark，第 2 页
  - `data/runs/benchmark/smoke1_p1/benchmark/run.json`
  - `data/runs/benchmark/smoke1_p1/benchmark/extraction-report.json`
  - `data/runs/benchmark/smoke1_p1/benchmark/translation-report.json`
- 2 页 extraction 量化结果
  - `data/runs/benchmark/direct_scored/benchmark/extraction-report.json`
- 量化报告对应的 gold 初稿
  - `data/runs/benchmark/direct_test/benchmark/annotations.gold.json`
- 未完成的 5 页批量验证
  - `data/runs/benchmark/split_test/benchmark/run.json`

## 限制与 caveat

这份纪要当前只能支持“阶段性结论”，还不能支持“最终定论”，原因有三：

1. `annotations.gold.json` 是由 `vision_structured` 自动播种生成的 draft
   - 文件路径：`data/runs/benchmark/direct_test/benchmark/annotations.gold.json`
   - 该文件的说明已经明确写出：**需要人工逐页复核后才能当作正式 gold 使用**。
2. 量化 extraction 结果当前只有 2 页样本
   - 能说明趋势，但样本规模还不够大。
3. 5 页批量 benchmark 还没有收敛
   - 当前 `data/runs/benchmark/split_test/benchmark/run.json` 仍停在 `status = started`
   - 这说明批量验证链路，尤其是 `direct` 路径，仍需继续诊断稳定性与耗时问题。

另外必须强调：

- `vision_direct` 在 extraction 报告里的较差分数，不能被解释为“多模态模型整体不行”。
- 更准确的解释是：它的输出目标不是“抽日文源文本”，而是“直接生成中文翻译”，因此不能把它和 extraction gold 做同类结论。
- external baseline 当前也只用于 translation 对比；不要把它的页级翻译输出拿去推导 extraction 优劣。

## 下一步建议

下一步主线不再是补充概念性讨论，而是继续工程诊断：

1. 继续压 `sample-size 5` 的 benchmark，把当前批量运行未收敛的问题定位清楚。
2. 重点检查 `direct` 路径在多页运行中的稳定性、耗时、是否存在 provider 请求级阻塞。
3. 在 extraction 侧继续保留 `vision_structured` 作为默认推荐主链路。
4. 在 translation 侧保留 `direct` 作为可选模式，但在更大样本验证完成前，不提升为默认模式。
5. 尽快把 `annotations.gold.json` 从 auto-seeded draft 升级为人工复核过的正式验证集，再做下一轮带分数的报告。

当前最稳妥的工程结论是：

**Phase 1 的 vision-first 主链路已经有可复现证据支持；其中 `vision_structured` 在 extraction 任务上明显优于 OCR 基线，而 translation 任务上 `structured` 与 `direct` 都可用，但 `direct` 质量波动更大，且当前 5 页批量验证尚未收敛。**
