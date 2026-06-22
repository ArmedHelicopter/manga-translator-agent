# Manga Translate Agent — PRD

> Product Requirements Document
> Version: 1.0
> Date: 2026-05-05

---

## 1. 产品概述

### 1.1 产品名称

**Manga Translate Agent** — 基于多模态 AI 的漫画翻译智能体

### 1.2 一句话描述

`mga` 是一个 external-first 的漫画翻译 Agent：以成熟 runtime 负责检测、OCR、擦字和嵌字，以 `mga` 自己的 artifacts、benchmark、OCR-aware translation、Vision enrichment、QA 与 memory/wiki 基础设施负责可审查性与长期差异化。

### 1.2.1 From Translation Engine to Character Simulation Agent

`mga` 不是传统意义上的漫画翻译器，而是一个在画面、文化与人物关系约束下，生成角色一致性对白的 Agent。

这意味着它处理的核心单位，不该只是“句子”或“气泡”，而应该是：

> 某个角色，在某个章节阶段，面对某个对象，带着某种情绪和权力关系，会如何在目标语言里说出这句话。

传统系统主要优化的是语言映射；`mga` 试图优化的是人格模拟、关系约束与连续章节中的角色稳定性。

### 1.2.2 Why External-First

`mga` 近期不把“从零重写整条漫画翻译 runtime”当成产品目标，而把它当成工程风险控制问题。

原因很直接：

- 检测、OCR、擦字、嵌字这些 runtime 能力已经有成熟开源底盘
- 当前最稀缺的不是又一个 runtime，而是可审查 artifacts、统一 benchmark、OCR/runtime 中间层、角色一致性翻译与 QA 审查
- 先改造成熟 external runtime，能更快验证用户价值，也能避免把大量时间耗在低差异化基础设施上

因此本项目近期采用：

- **runtime commodity**：复用成熟 runtime
- **intelligence proprietary**：把角色一致性、关系约束、学习与审查做成 `mga` 自己的核心资产
- **single runtime focus**：停止把 internal runtime 作为产品实现主线，避免双线消耗

> **修订 —— runtime 不再是黑盒。** 「runtime commodity」指默认**复用** runtime，而非**禁止**改它。当 runtime 的真实 bug 卡住交付（例：`_draw_footnotes` 硬编码 Linux Noto 字体 → Windows 脚注 tofu 乱码，且反复回归），**允许直接修改本地 runtime `manga_translator/`**（mga 以 `cwd=project_root` 调用 `python -m manga_translator`，用的就是这份 worktree 本地副本）。优先 mga 侧修；不行就改 `manga_translator/`。详见 `docs/render_purity_contract.md`（Edit scope）。

### 1.3 目标用户

| 用户类型 | 场景 | 核心需求 |
|---------|------|---------|
| **粉丝汉化组** | 翻译连载漫画新章节 | 快速出稿、角色语言一致、能复用已有翻译风格 |
| **个人漫画爱好者** | 翻译自己喜欢的作品 | 低门槛、支持常见格式、质量可接受 |
| **漫画出版/本地化团队** | 批量翻译漫画 | 高质量、可校对、支持协作流程 |
| **语言学习者** | 双语对照阅读 | 双语对照输出、原文可查 |

### 1.4 核心价值主张

1. **角色一致性**：翻译目标不是单句正确，而是角色在连续章节中的语言稳定
2. **关系约束**：称呼、敬语、语气和情绪推进受人物关系与场景约束
3. **翻译学习**：从已有汉化学习的不只是词汇映射，更是角色在中文中的人格质感
4. **QA 审查**：不仅查事实错漏，也查人设崩坏、关系层级错位和语气漂移
5. **OCR + Vision 分工**：OCR/runtime 提供可嵌字文本与几何，Vision 只补充框类型、视觉脚注和语言风格提示
6. **External-first delivery path**：短期优先借力成熟 runtime 交付结果，而不是重复造轮子
7. **文化适配**：造词、敬语、拟声词、文化概念分级处理
8. **供应商自由**：云端/本地模型随意切换，无锁定
9. **格式全支持**：图片/PDF/EPUB/MOBI/CBR/CBZ

---

## 2. 问题与机会

### 2.1 现有方案的痛点

| 痛点 | 现状 | 我们的方案 |
|------|------|-----------|
| OCR 降维丢失信息 | 图片→文本→翻译，视觉上下文丢失 | OCR 负责主文本，Vision enrichment 补充画面语境 |
| 角色语言无差异 | 所有角色同一翻译腔调 | 角色档案 + RAG |
| 缺少人格概念 | 只能优化句子，无法优化角色一致性 | 角色记忆 + 关系约束 + 连续章节校准 |
| 嵌字效果差 | 擦除留痕、排版生硬 | 智能擦除 + 气泡适配嵌字 |
| 文化适配为零 | 造词/敬语/拟声词直译了事 | 术语库 + 分级策略 |
| 虚构文字无法处理 | 咒语/深渊文字出乱码 | 虚构文字数据库 + 分类处理 |
| 供应商锁定 | 绑死单一翻译引擎 | 抽象层 + 多供应商 |
| 无学习能力 | 每次从头开始 | 翻译学习引擎 |

### 2.2 市场机会

- **开源最成熟方案**（manga-image-translator ⭐9845）用 OCR pipeline，无角色系统，嵌字质量一般
- **闭源市场空白**：没有端到端的通用漫画翻译产品（要么是底层 API，要么是内容平台，要么是老工具）
- **AI 多模态能力成熟**：GPT-4o / Gemini 2.5 已能同时处理图像理解 + 文字提取 + 翻译
- **漫画全球化需求增长**：韩漫 Webtoon、日漫数字发行、中国漫画出海

`mga` 的机会点不只是“把漫画翻译得更顺”，而是把翻译从句子转换提升为角色一致的跨语言再表演。

同时，`mga` 不把成熟开源 runtime 视为“必须打败的对象”，而把它们视为可以改造的底盘。近期最现实的策略不是推倒重写，而是在现有 runtime 上叠加 `mga` 的 artifacts、benchmark、review 与 intelligence layer。

---

## 3. 功能需求

### 3.1 P0 — 必须有（MVP）

| 功能 | 描述 | 验收标准 |
|------|------|---------|
| **external runtime 宿主** | 以成熟 runtime 完成检测、OCR、擦字、嵌字与基础翻译执行 | 默认主链能稳定输出翻译嵌字图片 |
| **运行产物归一化** | 把 external 输出收敛到 `mga` artifacts / reports | 每次运行都有可审查 run summary 与文本产物 |
| **基本嵌字交付** | 以 external runtime 产出可读译图 | 输出图片数量与输入页一致 |
| **图片格式支持** | 输入/输出 JPG/PNG | 批量处理目录下所有图片 |
| **CLI 入口** | 命令行工具 | `manga-translate input/ -o output/` 默认走 external-core |
| **provider 桥接** | 先桥接 OpenAI 配置到 external runtime | `mga` 能统一管理 base_url / model / key |
| **Vision enrichment** | OCR 成功后仍运行 Vision，补充文本框类型、作者绘制文字脚注、临时说话人和语言风格提示 | Vision 不覆盖 OCR 文本；漏检绘制文字只作为页级脚注 |

### 3.2 P1 — 应该有（核心差异化）

| 功能 | 描述 | 验收标准 |
|------|------|---------|
| **角色档案 RAG** | 每个角色独立的语言档案 | 翻译时注入角色口癖/称呼/语气；依赖可靠角色归属或人工绑定 |
| **QA 校对层** | 独立 LLM 校对翻译结果 | 每条建议带理由 + 置信度，并可指出人设漂移 |
| **格式扩展** | PDF/EPUB/CBR/CBZ 输入输出 | 能处理并保留原始格式 |
| **术语库** | per-work 作者造词/文化词库 | 术语统一翻译，并服务角色语域稳定 |
| **热启动** | 从已有翻译学习 | `--learn-from` 自动生成档案并校准人格质感 |
| **反幻觉** | 翻译锚定到气泡编号 | 修改必须引用 bubble_id |

### 3.3 P2 — 可以有（高级特性）

| 功能 | 描述 |
|------|------|
| **关系图谱** | 角色关系图，驱动敬语层级匹配 |
| **文化适配层** | 敬语补偿、文化词分级策略 |
| **虚构文字** | 虚构书写系统的分类和处理 |
| **增量学习** | 翻译过程中持续更新角色档案 |
| **语言演化** | 检测并跟踪角色语言随剧情的变化 |
| **双语对照输出** | 左页原文/右页译文 PDF |
| **翻译报告** | JSON 格式的完整翻译记录 |

### 3.4 P3 — 未来规划

| 功能 | 描述 |
|------|------|
| **Web UI** | FastAPI + React 界面 |
| **角色档案可视化编辑器** | 图形化编辑角色语言档案 |
| **QA 审查界面** | 逐条接受/拒绝修改建议 |
| **批量处理 + 进度管理** | 长篇连载的批量翻译 |
| **插件系统** | 自定义翻译引擎、嵌字渲染器 |
| **MCP Server** | 供其他 AI agent 调用 |

---

## 4. 系统架构

### 4.1 整体架构

`mga` 的产品形态不是传统线性翻译 pipeline，而是一个以 artifact 为中心的 **Translation Graph**：external runtime 负责可交付底座，`mga` 负责围绕 `PageArtifact` / `BubbleArtifact` 构建 OCR/Vision 双感知流、智能工作区、对白生成和 QA/repair 闭环。

```
external runtime layer
  → 检测 / OCR / 擦字 / 嵌字 / render-only 交付底盘

mga artifact spine
  → PageArtifact / BubbleArtifact / RunManifest / RenderContract

mga intelligence graph
  → OCR-aware understanding / Vision enrichment / memory / relation / culture / QA / learning

mga dialogue realization
  → semantic translation → persona rendering → review / repair
```

核心结构：

```
┌─────────────────────────────────────────────────────────┐
│                    Delivery Shell                        │
│  format adapter / runtime bridge / render-only / output  │
│                                                         │
│  ┌───────────────────────────────────────────────────┐  │
│  │                Artifact Spine                      │  │
│  │  PageArtifact / BubbleArtifact / RunManifest       │  │
│  │                                                   │  │
│  │  ┌─────────────────────────────────────────────┐  │  │
│  │  │             Intelligence Core                │  │  │
│  │  │ memory / relation / culture / QA / learning  │  │  │
│  │  │                                             │  │  │
│  │  │  ┌───────────────────────────────────────┐  │  │  │
│  │  │  │        Dialogue Realization            │  │  │  │
│  │  │  │ semantic meaning → persona rendering   │  │  │  │
│  │  │  └───────────────────────────────────────┘  │  │  │
│  │  └─────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

近期推荐落地顺序：

1. 用 external runtime 跑通可交付链路，并保持 runtime artifact 作为主文本与几何权威。
2. 用 `mga` artifact spine 固化可审查的 page/bubble/run/render contract。
3. 明确 OCR 与 Vision 是并行感知流：OCR/runtime 提供 `source_text` 与 `bbox`；Vision 只补充框类型、视觉脚注、临时说话人、语气和场景提示。
4. 先在当前线性执行器中模拟 Translation Graph：把现有 translation brain 内部拆成 semantic translation 与 persona rendering，并写出 trace。
5. 等效果验证后，再把 semantic/persona/QA repair 升格为独立 graph nodes，逐步用 artifact dependency 替代固定 stage order。

当前正式产品语义：

- `external-first delivery path`：唯一正式产品主线
- `internal`：历史验证资产与参考实现，不再作为产品实现路线继续推进

### 4.2 供应商架构

```
LLMProvider (抽象基类)
├── OpenAIProvider
├── GeminiProvider
├── AnthropicProvider
├── DeepSeekProvider
├── OllamaProvider (本地)
├── LMStudioProvider (本地)
└── VLLMProvider (本地)

每个 Stage 可独立选择供应商。
配置文件：providers.toml
CLI 当前可用覆盖：--provider / --config；stage-level 路由来自 providers.toml
```

### 4.2.1 当前实现状态

| 能力 | 当前状态 |
|------|---------|
| OCR/runtime 主文本 | 已接线；runtime artifact 是气泡文本和几何的权威来源 |
| Vision enrichment | 已接线；补充框类型、视觉脚注、临时说话人和语言风格提示 |
| Translation brain | 已接线；当前仍是 semantic translation 与 persona rendering 的混合体；下一步先在内部拆分两步并写出 trace |
| Dialogue realization | 设计目标：语义层只负责忠实转换，人格层再根据角色、关系、场景和 Vision hints 渲染对白 |
| QA | 已接线；当前是 review layer v0，后续拆成 semantic QA / persona QA / layout QA，并由 repair planner 路由回对应节点 |
| 角色归属 | 已有保守最小实现；只把与既有角色档案强匹配的 hint 提升为正式 `speaker_id`，模糊 provisional_speaker 只写 trace |
| 角色 RAG / 关系图谱 | 角色记忆已有最小闭环：已有正式 `speaker_id` 时，同次多页运行会更新角色记忆并注入后续页；关系图谱与自动归属仍需补强 |
| Learning engine | 模块与 mock 测试存在；真实漫画热启动闭环仍需端到端验证 |
| legacy compatibility CLI | `manga_translate.cli` 仍保留 external-core 兼容路径，不代表 `manga-translate` 产品主链 |

### 4.3 数据流

```
项目目录/
├── originals/               # 原始漫画
├── translations/            # 页级与区域级翻译结果
├── terminology/             # 作品术语资产
├── style_guide.toml         # 翻译风格指南
├── voice_changelog.toml     # 角色语言演化日志
├── project_meta.toml        # 项目元数据
└── memory/
    ├── state/               # runtime canonical source
    │   ├── characters/
    │   ├── scenes/
    │   ├── terms/
    │   ├── decisions/
    │   └── index.json
    ├── characters/          # 角色 wiki projection
    ├── scenes/              # 场景 wiki projection
    ├── terms/               # 术语 wiki projection
    ├── decisions/           # 决策 wiki projection
    └── indexes/             # 入口页与索引页
```

其中：

- `memory/state/` 是运行时唯一真相源
- `memory/*` 的 Markdown 页是 human-readable projection + annotation layer
- repo `docs/` 只保留 ADR、模板、规范与示例，不作为真实作品记忆目录

---

## 5. 非功能需求

### 5.1 性能

| 指标 | 目标 |
|------|------|
| 单页处理时间 | < 30 秒（云端 Vision + Translation） |
| 单话处理时间（20 页） | < 15 分钟 |
| 本地模型单页 | < 60 秒 |
| 内存占用 | < 2 GB（不含模型加载） |

### 5.2 质量

| 指标 | 目标 |
|------|------|
| 气泡检测准确率 | > 95% |
| OCR 文字提取准确率 | > 98%（标准日文；以 runtime OCR 为准） |
| Vision enrichment 命中率 | > 80%（框类型、视觉脚注、语言风格提示的人工抽样有效率） |
| 角色推理准确率 | 后续角色推理阶段指标；不作为 Vision enrichment 验收项 |
| QA 校对有效建议率 | > 70%（人工评估） |
| 角色一致性可感知 | 同一角色跨页语言风格稳定 |
| 关系语气稳定性 | 对不同对象的称呼/敬语切换符合预期 |
| 人设偏移识别有效性 | QA 能发现明显的角色口吻漂移 |

### 5.3 兼容性

- Python 3.10+
- Linux / macOS / Windows (WSL)
- 支持 Docker 部署
- 支持无 GPU 环境（云端模式）

### 5.4 安全与隐私

- 本地模式下所有数据不出本机
- 云端模式下图片发送至供应商 API（明确告知用户）
- 不上传角色档案和翻译历史到云端
- API key 安全存储（环境变量或 .env 文件）

---

## 6. CLI 接口设计

```bash
# 基本用法：翻译图片目录（默认 external-core）
manga-translate input/ -o output/

# 指定输出格式
manga-translate input.pdf -o output.pdf --format pdf
manga-translate input/ --format epub -o output.epub
manga-translate input.cbr --format cbz -o output.cbz

# 热启动：从已有翻译学习
manga-translate new_ch/ --learn-from existing_translated/ -o output/

# 纯学习模式
manga-translate existing/ --learn-only --learn-from existing/ -o output/

# 供应商选择
manga-translate input/ --provider openai
manga-translate input/ --provider openai --config configs/providers.toml

# 双语对照
manga-translate input/ --format bilingual -o bilingual.pdf

# 指定翻译方向
manga-translate input/ --lang ja-zh        # 日→中（默认）
manga-translate input/ --lang ko-zh        # 韩→中
manga-translate input/ --lang en-zh        # 英→中

# 项目管理
manga-translate profile list               # 查看角色档案
manga-translate term list                  # 查看术语库

# 调试与详细输出
manga-translate input/ -v                  # verbose
manga-translate input/ --save-json         # 保留额外 JSON artifact
manga-translate benchmark-external input/ -o output/
manga-translate legacy benchmark-extraction input/ -o output/
```

---

## 7. 实现路线图

| Phase | 内容 | 交付物 |
|-------|------|--------|
| **Phase 1** | 图片目录 MVP | 可审查 page contract、OCR/runtime 主文本、Vision enrichment、图片 I/O |
| **Phase 1.5** | external-first 交付链路 | 把 `manga-image-translator` 固定为默认 runtime，完成 `benchmark-external`、same-page review、连续 5 页 smoke |
| **Phase 2** | external runtime 魔改 | 在 external runtime 上插入 `mga` 的 prompt-orchestrated generation |
| **Phase 3** | 翻译学习引擎 | `--learn-from` + 人格校准；作为 intelligence layer 热启动入口 |
| **Phase 4** | 角色系统 + QA | 角色档案 RAG、角色归属推理、关系约束、角色一致性翻译、QA |
| **Phase 5** | 文化适配与格式扩展 | 术语库、造词发现、敬语补偿、更多格式支持 |
| **Phase 6** | 对 external runtime 的更深改造 | 在已有宿主上继续强化 QA、memory、渲染与审计能力 |

### 7.1 发布纪律

- 任何 release commit/tag 前，必须确认本地 secret 未被追踪
- `configs/providers.toml`、本地 venv、`data/`、`external/`、benchmark/debug/review 输出必须保持忽略
- external vendor repo 不得混入版本库
- 大体积 benchmark/debug artifacts 默认不纳入 release，只保留必要文档与可复现脚本

---

## 8. 成功指标

| 阶段 | 指标 | 目标 |
|------|------|------|
| MVP | 能跑通日漫翻译全流程 | 一页漫画 → 翻译嵌字成品 |
| v1.0 | 角色一致性可感知 | 同一角色不同页语言风格一致，面对不同对象时语气切换成立 |
| v1.0 | 热启动可用 | 10 话已有翻译 → 自动提取档案 → 翻译新话 |
| v2.0 | 嵌字质量可接受 | 无明显补丁感，文字可读 |
| v2.0 | 文化适配有效 | 造词统一、敬语正确 |

---

## 9. 竞品对比

| 维度 | manga-image-translator | BallonsTranslator | 本项目 |
|------|----------------------|-------------------|--------|
| 架构 | OCR pipeline | OCR pipeline (GUI) | OCR/runtime-first + Vision enrichment |
| 角色系统 | △ | △ | 人工 `speaker_id` 下已有 page-sequential 记忆闭环；自动角色归属与成熟角色声线建模仍未完成 |
| 文化适配 | ❌ | ❌ | 术语库/分级模块存在，默认主链仍需真实作品验证 |
| 热启动 | ❌ | ❌ | 学习引擎模块存在，真实漫画闭环待验证 |
| 校对层 | ❌ | ❌ | 独立 QA stage 已接线 |
| 供应商 | 多但绑定 | 同左 | 自由切换 |
| 格式 | 图片目录 | 图片目录 | 全格式 |
| 嵌字 | ⭐⭐⭐ | ⭐⭐⭐⭐ | Phase 2 优化 |

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| Vision 模型成本高 | 长篇连载费用大 | 支持本地模型 + 缓存机制 |
| 嵌字质量不达预期 | 用户体验差 | Phase 2 专项优化，支持手动调整 |
| 角色推理不准 | 翻译一致性差 | 后续角色归属阶段引入人工校正接口 + 渐进学习；Vision enrichment 不承担最终归属 |
| 虚构文字无对照表 | 部分作品翻译不完整 | 社区共建数据库 |
| MOBI 格式依赖 Calibre | 用户安装门槛 | 优雅降级，提示安装 |

---

## 11. 术语表

| 术语 | 含义 |
|------|------|
| Vision enrichment | 多模态视觉模型补充画面理解、脚注和语言风格提示，不替代 OCR 主文本 |
| OCR-aware translation | 翻译阶段以 OCR/runtime 文本为主输入，同时消费 Vision/memory/cultural hints |
| RAG | Retrieval-Augmented Generation，检索增强生成 |
| 热启动 | 从已有翻译中学习模式后开始翻译 |
| 冷启动 | 无已有翻译，从零建立档案 |
| 嵌字 | 将翻译文字嵌入漫画气泡中 |
| 口癖 | 角色特有的说话习惯 |
| 造词 | 作者创造的虚构词汇 |

---

*PRD v1.0 — 待迭代*
