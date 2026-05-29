# MGA 最终产品交付路线图

> 日期：2026-05-22
> 状态：runtime-first integration in progress

---

## 现状总览

代码库已实现多数组件雏形：Models / Providers / Formats / Memory+Wiki+Graph / Cultural / QA / Pipeline / CLI / Runtime Bridge(two-pass) / Learning Engine / Novel Mode。当前重点是把默认漫画链路收敛为 OCR/runtime 主文本 + Vision enrichment，并明确哪些 intelligence 能力已经进入主链、哪些仍只是模块雏形。

当前确认：

- `manga-translate = mga.cli.main:main` 是产品主入口。
- 漫画模式会执行 runtime artifact export，然后把 `.mga-payload` 传给 `PipelineOrchestrator`。
- 默认 pipeline 已包含 `OCRArtifactStage`、`VisionEnrichmentStage`、Character/Cultural、Translation、QA、Render、Output。
- Vision enrichment 已接线，但只做 metadata/脚注/语气提示，不做主 OCR。
- 默认漫画主链已有保守 `SpeakerAttributionStage`：只把强匹配既有角色档案的 hint 提升为正式 `speaker_id`，并写出 attribution trace。
- 默认漫画主链在正式 `speaker_id` 存在时，已有最小 page-sequential 角色记忆闭环：翻译会更新 `CharacterState`，后续页会读取更新后的风格上下文，并写出 `character_memory` trace。
- 角色关系图谱、学习引擎、增量翻译有模块和测试，但成熟自动角色归属、成熟声线摘要和真实漫画热启动闭环仍待补强。
- `manga_translate.cli` 是 legacy compatibility shim，仍只代表 external-core 兼容路径，不代表当前产品主链。

---

## 6 模块交付计划（持续收敛）

### 模块 A：Artifacts 归一化 + 翻译报告

**目标**：每次运行产出可审查的完整产物链

| 交付物 | 文件 | 说明 |
|--------|------|------|
| Run Summary | `mga/artifacts/run_summary.py` | 已有：`run.json` 写入；仍需补强 provider/runtime 细节 |
| Translation Report | `mga/artifacts/translation_report.py` | 已有：每条翻译的 bubble_id、原文、译文；QA/cultural 字段继续收敛 |
| Review Diff | `mga/review/diff.py` | 原文 vs 译文 diff，人工审查格式 |
| CLI 接入 | `--save-json` 参数 | 已接线；产出 `run.json` + `translation-report.json` |
| Tests | `tests/artifacts/` | artifact 生成 + 报告格式验证 |

**验收**：`manga-translate input/ -o output/ --save-json` 产出完整产物；review diff 入口仍需补齐

**依赖**：无，立即可做

---

### 模块 B：翻译学习引擎（热启动）

**目标**：从已有翻译中自动提取角色档案、术语库、风格指南

| 交付物 | 文件 | 说明 |
|--------|------|------|
| Aligner | `mga/learning/aligner.py` | Stage L1: 双页对齐（文件名匹配 + 视觉验证） |
| Dual Vision | `mga/learning/dual_vision.py` | Stage L2: 双页视觉理解 |
| Pattern Extractor | `mga/learning/pattern_extractor.py` | Stage L3: 角色语言/术语/风格/关系 |
| Validator | `mga/learning/validator.py` | Stage L4: 一致性/完整性检查 |
| Engine | `mga/learning/engine.py` | L1-L4 编排 |
| CLI | `--learn-from` / `--learn-only` | 已接线到 `LearningEngine`；真实漫画热启动闭环待验证 |
| Auto-gen | `character_profiles/` + `terminology/` + `style_guide.toml` + `character_graph.json` | 学习产出 |
| Tests | `tests/learning/` | 对齐 + 提取 + 端到端 mock |

**验收**：`manga-translate ch11/ --learn-from ch01_to_10_translated/ -o output/` 自动提取档案并翻译；当前仍需真实样本端到端验证

**依赖**：模块 A

---

### 模块 C：角色档案 RAG + 翻译注入

**目标**：翻译时真正使用角色档案，实现角色一致性

| 交付物 | 文件 | 说明 |
|--------|------|------|
| Profile Loader | `mga/memory/profile_loader.py` | 从 TOML 加载档案到翻译上下文 |
| Profile Builder | `mga/memory/profile_builder.py` | 从 CharacterState 自动生成/更新 TOML |
| Translation 注入 | `translation_stage.py` + `mga/memory/character_memory_updater.py` | 已读取 memory context；已有 speaker 时会按页更新角色记忆并注入后续页 |
| 角色归属推理 | `speaker_attribution_stage.py` | 已有保守最小实现；Vision provisional_speaker 不能直接等同最终角色归属 |
| 反幻觉 | `mga/memory/hallucination_guard.py` | 翻译必须引用 bubble_id，修改必须带理由 |
| CLI | `profile list/edit` 完善 | 角色档案管理 |
| Tests | `tests/memory/test_character_memory_updater.py` + `tests/pipeline/test_page_sequential_memory_integration.py` | 最小角色记忆闭环 + 注入回归 |

**验收**：已完成最小验收：同次多页运行中，page 1 的正式 speaker 翻译会更新角色记忆，page 2 能读到该风格上下文。完整验收仍待补齐：同一角色面对不同对象时的稳定自称/称呼/语气切换，以及 QA 检测人设崩坏。

**依赖**：模块 B

---

### 模块 D：角色关系图谱

**目标**：跨角色关系约束网络，驱动敬语匹配

| 交付物 | 文件 | 说明 |
|--------|------|------|
| Graph | `mga/memory/graph.py` | NetworkX 关系图谱（节点=角色，边=关系+敬语+演化） |
| Graph Builder | `mga/memory/graph_builder.py` | 从翻译历史/学习结果构建 |
| Graph Retrieval | `mga/memory/graph_retrieval.py` | 查询角色对关系路径和敬语规则 |
| 关系驱动翻译 | 修改 `translation_stage.py` | 部分读取 graph retrieval；listener/speaker 推理仍很浅 |
| Evolution Tracker | `mga/memory/evolution_tracker.py` | 称呼降级/语气变化检测 |
| Tests | `tests/memory/test_graph_*.py` | 构建 + 查询 + 敬语匹配 |

**验收**：灯对的場称呼降级时翻译自动跟随；演化写入 `voice_changelog.toml`

**依赖**：模块 C

---

### 模块 E：文化适配深化 + 造词发现

**目标**：自动发现造词，按分级策略处理文化词汇

| 交付物 | 文件 | 说明 |
|--------|------|------|
| Coinage Detector | `mga/cultural/coinage_detector.py` | 造词自动检测 |
| Term Classifier | `mga/cultural/term_classifier.py` | 7 级分级策略 |
| Vision enrichment | 修改 `vision_stage.py` | 已接线：输出文本框类型、视觉脚注、临时说话人、语言风格提示；不覆盖 OCR 文本 |
| Translation 增强 | 修改 `translation_stage.py` | 按策略处理，输出标注 |
| Cultural QA | `mga/cultural/qa_check.py` | 术语一致性 + 策略一致性 |
| Fictional Script | `mga/qa/fictional_script.py` | 虚构文字分类与处理 |
| Tests | `tests/cultural/test_coinage_*.py` | 检测 + 分级 + 虚构文字 |

**验收**：Vision 识别「硝子継ぎ」为造词标记 literal 策略；翻译按策略处理；QA 检查术语统一。当前 Vision enrichment 不承担主术语发现闭环。

**依赖**：模块 B（需术语库）

---

### 模块 F：增量翻译 + 双语输出 + 批量处理

**目标**：产品完整性——连载场景支持

| 交付物 | 文件 | 说明 |
|--------|------|------|
| Incremental | `mga/pipeline/incremental.py` | 模块存在；默认漫画 CLI 主链未以它作为入口 |
| 持续学习 | 修改 `memory/learn.py` | 翻译过程中持续更新档案 |
| Bilingual PDF | `mga/format/bilingual_pdf.py` | 左页原文/右页译文 |
| Batch | `mga/pipeline/batch.py` | 多章节并行、断点续翻 |
| CLI | `--bilingual` / 批量输入 | 完整 CLI 支持 |
| Tests | `tests/pipeline/test_incremental_*.py` | 增量 + 双语 + 批量 |

**验收**：第 11-20 话自动加载前 10 话档案；翻译中档案持续更新；`--bilingual` 输出双语 PDF

**依赖**：模块 A-E

---

## 执行顺序

```
A (Artifacts) ──→ B (学习引擎) ──→ C (角色 RAG) ──→ D (关系图谱)
                                         │
                                         └──→ E (文化深化) ──→ F (增量/双语/批量)
```

- A：无依赖，立即可做
- B：依赖 A
- C：依赖 B
- D：依赖 C，可与 E 并行
- E：依赖 B，可与 D 并行
- F：依赖 A-E

## 质量门禁

每个模块完成时：
1. 所有现有 134+ tests 仍通过
2. 新模块 tests 全部通过
3. 手动 smoke test 通过（CLI 端到端）
4. 代码 review 无 blocking issue
