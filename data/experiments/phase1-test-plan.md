# 阶段1实验计划：Semantic 并行验证

## 实验目标

验证 Semantic 并行翻译的性能收益和质量保证，为阶段2（分批递推）提供决策依据。

---

## 测试数据集准备

### 来源
从 `./data/input/*.pdf` 中抽取 **10页** 作为测试集。

### 选择标准
- ✅ 包含至少 **3个角色** 的对话
- ✅ 包含至少 **1个情绪转折点**（如从平静到愤怒）
- ✅ 包含 **片假名术语**（测试术语一致性）
- ✅ 包含角色 **口癖或特殊语气**（测试记忆累积）
- ✅ 页面气泡数量 4-6 个（代表典型漫画密度）

### 数据集路径
```
data/experiments/phase1-test-set/
├── page_01.jpg
├── page_02.jpg
├── ...
└── page_10.jpg
```

---

## 实验设计

### 实验1：性能基准测试

**目的**: 测量 Semantic 并行的时间节约

**步骤**:
1. 运行串行模式（baseline）
   ```bash
   manga-translate data/experiments/phase1-test-set/ \
     -o output/baseline/ \
     --mode serial \
     --log-level INFO
   ```
   记录：
   - 总时间
   - 每阶段时间（Format, Vision, Translation, QA, Render）
   - Translation 内部分解（Semantic, Persona, Memory）

2. 运行 Semantic 并行模式
   ```bash
   manga-translate data/experiments/phase1-test-set/ \
     -o output/semantic-parallel/ \
     --parallel semantic \
     --max-concurrent-requests 5 \
     --log-level INFO
   ```
   记录同上。

3. 对比分析
   - 总时间节约百分比
   - Semantic 阶段加速比（理论 5x vs 实际）
   - 并发效率 = 实际加速 ÷ 理论加速
   - 是否有超时或失败任务

**预期结果**:
- 总时间：1073s → < 700s（节约 > 35%）
- Semantic 阶段加速比：3.5-4.5x（考虑并发开销）
- 并发效率：> 70%

---

### 实验2：翻译质量对比

**目的**: 验证并行模式不影响翻译质量

**步骤**:
1. 提取翻译文本
   ```bash
   # 从 output/{baseline,semantic-parallel}/manifest.json 提取
   python scripts/extract_translations.py output/baseline/ > baseline.txt
   python scripts/extract_translations.py output/semantic-parallel/ > parallel.txt
   ```

2. 逐气泡对比
   - 文本是否完全一致？
   - 如有差异，记录差异气泡ID和内容

3. 人工质量评估（盲测）
   - 随机抽取 20 个气泡
   - 两个版本混排，请人类评估哪个质量更好
   - 记录：parallel更好 / baseline更好 / 相同

**预期结果**:
- 文本一致性 > 99%（允许微小标点差异）
- 盲测：parallel 和 baseline 质量评分相同

---

### 实验3：记忆更新一致性

**目的**: 验证 Persona 串行执行保持了记忆累积正确性

**步骤**:
1. 提取记忆状态
   ```bash
   # 从 output/{baseline,semantic-parallel}/memory/state/character_*.json
   python scripts/compare_memory.py output/baseline/memory/ output/semantic-parallel/memory/
   ```

2. 对比检查项
   - 角色档案的 `speech_patterns` 是否一致？
   - `catchphrases` 出现顺序是否一致？
   - `tone_spectrum` 是否一致？
   - `evolution` 时间线是否一致？

**预期结果**:
- 记忆状态完全一致（JSON diff 为空）

---

### 实验4：并发安全性测试

**目的**: 检测竞态条件、死锁、资源泄漏

**步骤**:
1. 压力测试（重复运行10次）
   ```bash
   for i in {1..10}; do
     manga-translate data/experiments/phase1-test-set/ \
       -o output/stress-test-$i/ \
       --parallel semantic \
       --max-concurrent-requests 10
   done
   ```

2. 检查
   - 是否有运行失败？
   - 10次运行的翻译结果是否一致？
   - 是否有内存泄漏（监控进程内存）
   - 是否有孤儿线程未关闭

**预期结果**:
- 10次运行全部成功
- 翻译结果完全一致
- 无内存泄漏或线程泄漏

---

### 实验5：错误处理与降级

**目的**: 验证异常场景的鲁棒性

**步骤**:
1. 模拟 Provider 超时
   ```bash
   # 在 config.toml 设置极短超时
   [translation]
   parallel_mode = "semantic-parallel"
   semantic_timeout = 1  # 1秒必定超时
   ```
   预期：自动降级到串行模式，输出警告日志

2. 模拟 Provider 部分失败
   - Monkeypatch 某些调用抛出异常
   - 预期：收集错误，降级到串行模式

3. 模拟网络不稳定
   - 使用 `tc` 命令限制网络带宽
   - 预期：并发效率下降，但翻译成功

**预期结果**:
- 降级机制正常工作
- 不会因为并行失败而中断整个流程

---

## 实验环境

### 硬件
- CPU: 建议 4核以上（支持并发）
- 内存: ≥ 8GB
- 网络: 稳定的互联网连接

### 软件
- Python: 3.10+
- 已安装依赖: `pip install -e ".[dev]"`
- Provider: OpenAI API（确保有足够配额）

### 配置
```toml
# configs/phase1-experiment.toml

[translation]
parallel_mode = "semantic-parallel"
max_concurrent_requests = 5
semantic_timeout = 60

[llm]
primary_provider = "openai"
primary_model = "gpt-4o-mini"
```

---

## 数据收集模板

### 性能数据

| 指标 | 串行模式 | Semantic并行 | 提升 |
|------|----------|--------------|------|
| 总时间 (s) | | | |
| Translation阶段 (s) | | | |
| - Semantic (s) | | | |
| - Persona (s) | | | |
| - Memory更新 (s) | | | |
| 其他阶段 (s) | | | |
| Semantic加速比 | 1.0x | | |
| 并发效率 (%) | - | | |

### 质量数据

| 指标 | 结果 | 说明 |
|------|------|------|
| 文本一致性 (%) | | 完全相同的气泡百分比 |
| 记忆状态一致性 | ✅/❌ | JSON diff是否为空 |
| 盲测评分差异 | | parallel - baseline |
| 术语一致性问题 | | 记录不一致的案例 |

### 异常记录

| 气泡ID | 问题类型 | 描述 | 影响 |
|--------|----------|------|------|
| | | | |

---

## 问题分类

实验员在测试过程中发现的问题，按以下分类上报：

### P0: 阻塞问题（必须修复）
- 翻译结果与串行版本显著不同
- 记忆更新顺序错误
- 死锁或崩溃
- 数据损坏

### P1: 性能问题（影响验收）
- 加速比 < 2.0x（未达到预期）
- 并发效率 < 60%
- 超时频繁

### P2: 质量问题（需要评估）
- 术语一致性下降
- 微小的翻译差异
- 日志不清晰

### P3: 改进建议（可延后）
- 配置项命名
- 错误消息改进
- 文档补充

---

## 报告格式

实验完成后，产出 `experiments/phase1-results.md`，包含：

1. **执行摘要**
   - 实验是否通过验收标准？
   - 关键指标总结（性能、质量）
   - 推荐：是否进入阶段2？

2. **详细数据**
   - 所有实验的数据表格
   - 性能曲线图（如有）
   - 差异样本展示

3. **问题清单**
   - 按 P0-P3 分类的问题列表
   - 每个问题的复现步骤
   - 建议的修复方案（可选）

4. **结论与建议**
   - 阶段1是否达到目标？
   - 阶段2的参数建议（如批大小）
   - 需要改进的配置或代码

---

## 时间计划

| 任务 | 预计时间 | 负责人 |
|------|----------|--------|
| 准备测试数据集 | 0.5h | 实验员 |
| 实验1: 性能基准 | 1h | 实验员 |
| 实验2: 质量对比 | 1h | 实验员 |
| 实验3: 记忆一致性 | 0.5h | 实验员 |
| 实验4: 并发安全性 | 1h | 实验员 |
| 实验5: 错误处理 | 0.5h | 实验员 |
| 撰写报告 | 1h | 实验员 |
| **总计** | **5.5h** | |

---

## 验收标准（重申）

阶段1通过验收需满足：

- ✅ 性能: 10页测试集翻译时间 < 700s（节约 > 35%）
- ✅ 质量: 翻译文本一致性 > 99%，记忆状态一致
- ✅ 稳定性: 10次重复运行无失败，无资源泄漏
- ✅ 测试: 所有单元测试通过，新增覆盖率 > 85%

如果验收通过，更新 `PARALLEL_TRANSLATION_PLAN.md` 状态为"✅ 阶段1完成"，启动阶段2。

如果验收未通过，记录阻塞问题，架构师与实现者协商修复方案。
