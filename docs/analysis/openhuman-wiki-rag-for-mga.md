# ADR: Project-Scoped Memory Wiki Layer for MGA

日期：2026-05-18

状态：accepted

## 1. Decision

`mga` 引入一个 **project-scoped memory wiki layer**，作为角色、术语、场景、翻译决策的长期记忆层。

该方案采用双层结构：

- **结构化层**：runtime canonical source
- **wiki 层**：human-readable projection + annotation layer

这层 memory 属于 `mga intelligence layer`，服务于：

- translation brain
- QA
- `--learn-from`
- 后续角色一致性与关系约束能力

真实作品记忆不存放在 repo `docs/` 中，而存放在 project/workspace 的 `memory/` 目录中。repo `docs/` 只保留 ADR、模板、规范和示例。

## 2. Context

`mga` 已经明确采用 external-first 主线：

- external runtime 负责近期交付能力
- `mga` 负责 orchestration 与 intelligence

当前产品真正需要解决的问题，不是“再做一个 runtime”，而是“如何把一次翻译判断沉淀成跨页、跨话、跨运行可复用的记忆”。

漫画翻译天然是长期任务。一个角色的：

- 自称
- 称呼体系
- 敬语层级
- 情绪爆发方式
- 对不同对象的语言切面
- 某个术语的采用理由

都会影响后续很多页和很多话。

这些信息不是单次 RAG 可以完全覆盖的，因为这里最重要的不是原始材料，而是**翻译判断本身**：

- 为什么这句不能直译
- 为什么这里必须保留关系距离
- 为什么这个称呼从这一话开始降级
- 为什么某个术语以后都必须统一

因此，`mga` 需要一层长期记忆，而不是只在每次翻译时临时检索。

## 3. Why This Is Not Just "More RAG"

这个方案不是“把向量库换个壳”，而是引入一层人和模型都能共同使用的翻译记忆。

分工如下：

- **结构化层**：负责稳定读写、过滤、索引、运行时消费
- **wiki 层**：负责可读、可审、可回滚、可人工修订
- **RAG/检索层**：负责在需要时召回相关记忆与证据

也就是说：

- wiki 负责“养知识”
- structured state 负责“稳定执行”
- retrieval 负责“找证据”

## 4. Alternatives Considered

### A. 纯结构化层，不要 wiki

优点：

- 工程实现最稳定
- 不存在双层同步问题
- runtime 读写路径清晰

缺点：

- 人工审阅与维护体验差
- 很难沉淀“为什么这么译”的决策理由
- QA 与译者难以把结构化记录直接当工作界面使用

结论：

不选。它适合作为底层，不适合作为完整记忆系统。

### B. 纯 wiki，wiki 作为真相源

优点：

- 人类可读性最好
- 修改门槛低
- 适合长期积累经验和注释

缺点：

- runtime 消费不稳定
- 校验、索引、过滤、变更检测都更脆弱
- 容易把自由文本误当数据库

结论：

不选。它不适合作为运行时唯一真相源。

### C. 双层结构：structured canonical + wiki projection

优点：

- runtime 路径稳定
- 人工审阅和解释能力强
- 允许后续逐步加 retrieval、QA、learn-from、索引和回写

缺点：

- 需要定义同步规则
- 需要避免结构化层与 wiki 层长期漂移

结论：

选这个。这是当前最平衡的方案。

## 5. Storage Model

真实运行期 memory 使用 project/workspace 目录，而不是 repo `docs/`。

推荐目录：

```text
memory/
├── state/
│   ├── characters/
│   ├── scenes/
│   ├── terms/
│   ├── decisions/
│   └── index.json
├── characters/
├── scenes/
├── terms/
├── decisions/
└── indexes/
```

职责：

- `memory/state/`：结构化真相源
- `memory/characters/`：角色 Markdown projection
- `memory/scenes/`：场景 Markdown projection
- `memory/terms/`：术语 Markdown projection
- `memory/decisions/`：决策 Markdown projection
- `memory/indexes/`：入口页、索引页、时间线页

repo 内的：

- `docs/characters/_template.md`
- `docs/scenes/_template.md`
- `docs/terms/_template.md`
- `docs/decisions/_template.md`
- `docs/indexes/_template.md`

仅作为模板和示例保留。

## 6. Source of Truth Rules

### 6.1 Canonical Rule

- runtime 只读取结构化 state
- wiki 不直接作为运行时输入

### 6.2 Projection Rule

- wiki 由结构化层自动投影生成
- wiki 可携带人工注释、解释性文本和审阅痕迹

### 6.3 Reverse Sync Rule

- 人工可以编辑 wiki
- 但这些改动必须通过显式 `sync/compile` 步骤回写结构化层
- 未同步的 wiki 改动不得直接进入 runtime

### 6.4 Conflict Rule

- 结构化层与 wiki 层冲突时：
  - runtime 以结构化层为准
  - 人工审阅以 wiki 为入口
  - 修复动作是同步回结构化层，而不是让 runtime 读自由文本

## 7. Entities

本轮只定概念，不写代码。

最小结构化实体：

- `CharacterState`
  - 角色标识
  - 章节适用范围
  - 自称
  - 对不同对象的称呼/敬语/语气切面
  - 口癖与句式特征
  - 最近修订信息
- `SceneState`
  - chapter/page/scene 标识
  - 关键角色
  - 情绪摘要
  - 关系变化
  - 关键对白引用
  - 对后续的影响
- `TermState`
  - 原词
  - 当前译法
  - 候选译法
  - 采用理由
  - 适用/不适用边界
  - 状态（draft/active/deprecated）
- `DecisionState`
  - 决策标题
  - 决策内容
  - 依据
  - 备选方案
  - 影响范围
  - 回滚条件
- `MemoryIndex`
  - 角色入口
  - 场景入口
  - 术语入口
  - 决策入口
  - 时间线或章节索引

与现有单次流水线模型的关系：

- `Page` / `Bubble` / `Utterance` / `TranslationCandidate`：单次运行内使用
- memory states：跨页、跨话、跨运行的长期记忆

## 8. Retrieval MVP

第一版 retrieval 不要求上向量库。

顺序定为：

1. 结构化过滤与索引查找
2. 关键词检索 wiki 页
3. 后续再加向量检索

理由：

- 先把 source-of-truth 和可读记忆层定稳
- 再增加召回复杂度
- 避免第一版把重心放到检索技术，而不是翻译记忆本身

## 9. Write-Back MVP

每页翻译完成后，最小回写顺序定为：

1. 结果写入 `translations/...`
2. 更新对应结构化 state
3. 生成或更新相应 wiki projection
4. QA 结果若形成长期判断，再落到 `DecisionState` / `SceneState` / `TermState`

这里强调：

- 先写 structured
- 再投影 wiki

而不是反过来。

## 10. Relationship to External-First

这个 memory/wiki 方案不改变当前 external-first 主线。

近期产品主线仍然是：

- external runtime 负责页级交付
- `mga orchestration layer` 负责 artifacts / benchmark / review
- `mga intelligence layer` 负责长期差异化

memory/wiki layer 属于 intelligence layer，不替代 external runtime，也不要求这阶段重写 runtime。

## 11. Non-Goals

本轮和第一版都不做：

- Obsidian 产品化
- UI 编辑器
- 全量知识图谱
- 自动关系图谱维护
- 双向无损自动同步
- 任意自由文本直接反推结构化 state

这些都可以是后续增强，但不是当前 memory/wiki 主线的第一阶段目标。

## 12. Consequences

### 好处

- 角色一致性、术语稳定、关系变化和翻译决策能长期沉淀
- QA 可以引用长期记忆，而不是只做单页检查
- 人和模型可以共享同一套可读记忆
- 后续 `learn-from` 和角色系统有明确落点

### 成本

- 需要维护 structured 与 wiki 两层
- 需要定义清楚同步与冲突规则
- 需要避免把模板目录和运行期数据目录混淆

## 13. Implementation Consequence for Future Work

后续实现应按这个顺序推进：

1. memory workspace 布局
2. 四类 note schema
3. `state/` 结构化 schema
4. structured-to-wiki projection
5. explicit sync API
6. minimal retrieval
7. write-back hooks from translation / QA output

在这之前，不应继续扩大 `docs/` 中的伪运行期结构，也不应把 wiki 直接当作 runtime 数据源。
