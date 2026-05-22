# MGA 最终产品交付路线图

> 日期：2026-05-22
> 状态：modules complete, integration shipped

---

## 现状总览

代码库已实现：Models / Providers(9) / Formats(6+novel) / Memory+Wiki+Graph / Cultural(7 strategies) / QA(9 proofreaders) / Pipeline(7 stages) / CLI / Runtime Bridge(two-pass) / Learning Engine(L1-L4) / Novel Mode。329 tests passing。

所有 6 模块已完成。两阶段渲染集成已实现（export-artifact + render-only）。

---

## 6 模块交付计划（全部完成）

### 模块 A：Artifacts 归一化 + 翻译报告

**目标**：每次运行产出可审查的完整产物链

| 交付物 | 文件 | 说明 |
|--------|------|------|
| Run Summary | `mga/artifacts/run_summary.py` | `run.json`：输入/输出/耗时/provider/页数/成功失败 |
| Translation Report | `mga/artifacts/translation_report.py` | 每条翻译的 bubble_id、原文、译文、置信度、QA findings、cultural strategy |
| Review Diff | `mga/review/diff.py` | 原文 vs 译文 diff，人工审查格式 |
| CLI 接入 | `--save-json` 参数 | 产出 `run.json` + `translation-report.json` |
| Tests | `tests/artifacts/` | artifact 生成 + 报告格式验证 |

**验收**：`manga-translate input/ -o output/ --save-json` 产出完整产物，可被 `mga review` 读取

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
| CLI | `--learn-from` / `--learn-only` | 热启动入口 |
| Auto-gen | `character_profiles/` + `terminology/` + `style_guide.toml` + `character_graph.json` | 学习产出 |
| Tests | `tests/learning/` | 对齐 + 提取 + 端到端 mock |

**验收**：`manga-translate ch11/ --learn-from ch01_to_10_translated/ -o output/` 自动提取档案并翻译

**依赖**：模块 A

---

### 模块 C：角色档案 RAG + 翻译注入

**目标**：翻译时真正使用角色档案，实现角色一致性

| 交付物 | 文件 | 说明 |
|--------|------|------|
| Profile Loader | `mga/memory/profile_loader.py` | 从 TOML 加载档案到翻译上下文 |
| Profile Builder | `mga/memory/profile_builder.py` | 从 CharacterState 自动生成/更新 TOML |
| Translation 注入 | 修改 `translation_stage.py` | prompt 注入自称/称呼/口癖/语气/关系切面 |
| 角色归属联动 | 修改 `character_stage.py` | 说话人归属与 profile 联动 |
| 反幻觉 | `mga/memory/hallucination_guard.py` | 翻译必须引用 bubble_id，修改必须带理由 |
| CLI | `profile list/edit` 完善 | 角色档案管理 |
| Tests | `tests/memory/test_profile_*.py` | 加载 + 注入 + 反幻觉 |

**验收**：同一角色面对不同对象，翻译的自称/称呼/语气有可感知差异；QA 检测人设崩坏

**依赖**：模块 B

---

### 模块 D：角色关系图谱

**目标**：跨角色关系约束网络，驱动敬语匹配

| 交付物 | 文件 | 说明 |
|--------|------|------|
| Graph | `mga/memory/graph.py` | NetworkX 关系图谱（节点=角色，边=关系+敬语+演化） |
| Graph Builder | `mga/memory/graph_builder.py` | 从翻译历史/学习结果构建 |
| Graph Retrieval | `mga/memory/graph_retrieval.py` | 查询角色对关系路径和敬语规则 |
| 关系驱动翻译 | 修改 `translation_stage.py` | A 对 B 说话时自动选择敬语层级 |
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
| Vision 增强 | 修改 `vision_stage.py` | 输出 coined_terms + cultural_terms |
| Translation 增强 | 修改 `translation_stage.py` | 按策略处理，输出标注 |
| Cultural QA | `mga/cultural/qa_check.py` | 术语一致性 + 策略一致性 |
| Fictional Script | `mga/qa/fictional_script.py` | 虚构文字分类与处理 |
| Tests | `tests/cultural/test_coinage_*.py` | 检测 + 分级 + 虚构文字 |

**验收**：Vision 识别「硝子継ぎ」为造词标记 literal 策略；翻译按策略处理；QA 检查术语统一

**依赖**：模块 B（需术语库）

---

### 模块 F：增量翻译 + 双语输出 + 批量处理

**目标**：产品完整性——连载场景支持

| 交付物 | 文件 | 说明 |
|--------|------|------|
| Incremental | `mga/pipeline/incremental.py` | 加载前文档案 → 翻译新章节 → 更新档案 |
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
