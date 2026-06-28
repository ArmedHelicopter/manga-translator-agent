# 并行翻译优化计划

## 目标

将10页漫画翻译时间从 1073s 优化到 ~400s，节约 **62%** 时间，同时保持翻译质量（角色语气连续性、术语一致性）。

## 核心策略：渐进式并行化

采用"欧拉递推"思路，分批并行翻译，批间使用上一批更新后的记忆，确保角色演变的连续性。

---

## 三阶段实施路线

### 阶段1：Semantic 并行（基础设施） ⏳ IN PROGRESS

**目标**: 验证并行翻译基础设施，降低风险

**策略**: 
- Semantic 翻译（事实层）全部并行执行
- Persona 翻译（语气层）保持串行，依赖实时累积记忆

**预期收益**:
- 时间: 1073s → ~650s（节约 39%）
- 质量风险: **零**（Persona 仍按顺序累积记忆）

**技术实现**:
- 修改 `TranslationStage._translate_page()` 支持批量 semantic 调用
- 新增 `mga/pipeline/parallel_executor.py` 处理并发调度
- 配置开关: `translation.parallel_mode = "semantic-parallel"`

**验证标准**:
- [ ] 10页测试集翻译时间 < 700s
- [ ] 所有 609 个单元测试通过
- [ ] 角色语气、术语翻译与串行版本一致
- [ ] 无并发竞态条件或死锁

**交付物**:
- ✅ `docs/architecture/phase1-semantic-parallel.md` (架构设计)
- ✅ `docs/architecture/phase1-handoff.md` (交付清单)
- ✅ `docs/experiments/phase1-test-plan.md` (实验计划)
- ✅ `mga/pipeline/parallel_executor.py` (并行调度器)
- ✅ `tests/pipeline/test_parallel_executor.py` (单元测试)
- ✅ 所有代码实现完成，720个测试通过
- ✅ 审计通过（最终裁决: PASS）
- 🔲 实验报告: `experiments/phase1-results.md` (等待实验员执行)

**状态**: 🟢 代码完成并通过审计，等待性能验证

---

### 阶段2：分批递推并行（欧拉式） 📋 PLANNED

**目标**: 大幅提升性能，保持可接受的质量权衡

**策略**:
```
M₀ = 章节初始记忆

批次1: 页[1,2] 并行翻译(semantic+persona)，使用 M₀
       → 串行更新记忆 → M₁

批次2: 页[3,4] 并行翻译，使用 M₁
       → 串行更新记忆 → M₂
       
...

批次5: 页[9,10] 并行翻译，使用 M₄
       → 串行更新记忆 → M₅ (最终)
```

**预期收益**:
- 批大小=2: 时间 ~600s（节约 44%）
- 批大小=3: 时间 ~407s（节约 62%）⭐ 推荐
- 批大小=5: 时间 ~290s（节约 73%）

**质量权衡**:
- 批内页面无法看到彼此的记忆更新
- 漫画通常2-3页是一个"节奏单元"，批内语气变化较小
- 批间边界清晰，重大转折能被下一批立即捕获

**技术实现**:
- 新增 `mga/pipeline/batch_scheduler.py` (批次调度)
- 扩展 `ParallelExecutor` 支持 persona 并行
- 配置参数: `translation.batch_size = 3`
- 批内记忆更新策略: 串行累积（保持时间顺序）

**验证标准**:
- [ ] 批大小2/3/5的性能曲线符合预期
- [ ] 批内术语不一致率 < 5%
- [ ] 角色语气突变仅发生在剧情转折点
- [ ] 人工盲测: 批次翻译 vs 串行翻译无明显质量差异

**交付物**:
- `docs/architecture/phase2-batch-parallel.md`
- `mga/pipeline/batch_scheduler.py`
- `tests/pipeline/test_batch_scheduler.py`
- 实验报告: `experiments/phase2-batch-size-tuning.md`

**状态**: ⚪ 计划中（依赖阶段1完成）

---

### 阶段3：自适应批大小（可选优化） 💡 FUTURE

**目标**: 根据内容动态调整批大小，平衡性能与质量

**策略**:
- 章节开头/过渡段落: 大批次（批大小=5）
- 对话密集/情绪转折: 小批次（批大小=2）
- 基于 `scene_context` 的"情绪梯度"自动判断

**预期收益**:
- 时间: ~350s（节约 67%）
- 质量: 接近串行版本

**技术实现**:
- 新增 `mga/pipeline/adaptive_batcher.py`
- 情绪梯度检测: 基于 VisionEnrichmentStage 的 scene_summary
- 配置: `translation.adaptive_batching = true`

**验证标准**:
- [ ] 自动批次划分与人工划分的一致性 > 80%
- [ ] 性能/质量达到帕累托最优

**状态**: ⚪ 未启动（取决于阶段2实验结果）

---

## 实验验证流程

### 测试集准备

从 `./data/input/*.pdf` 抽取10页，要求：
- 包含多个角色对话
- 包含至少1个情绪转折点
- 包含片假名术语（测试术语一致性）

### 验证维度

**1. 性能指标**
- 总翻译时间
- 每阶段耗时分解（semantic, persona, 记忆更新）
- 并发效率（理想并行 vs 实际并行）

**2. 质量指标**
- **角色语气一致性**: 同一角色在不同页的语气特征（敬语、口癖、句式）
- **术语一致性**: 同一片假名在不同页的中文翻译
- **记忆累积正确性**: 后续页是否继承前序页的角色学习
- **冲突检测**: 批内/批间的不一致案例数量

**3. 回归测试**
- 609个单元测试全部通过
- 端到端翻译输出与baseline对比（diff < 10%）

### 实验员任务

在每个阶段完成后：

1. 运行性能基准测试
   ```bash
   manga-translate data/test-10pages/ -o output/baseline/ --mode serial
   manga-translate data/test-10pages/ -o output/phase1/ --mode semantic-parallel
   ```

2. 生成对比报告（不改代码，只记录）
   - 时间对比
   - 质量问题列表（角色名不一致、语气突变、术语分歧）
   - 推荐的批大小或配置调整

3. 上报问题到 `experiments/phaseN-issues.md`

---

## 风险与应对

### 风险1: 并发竞态条件

**描述**: 多线程/进程访问共享状态（如 `ProviderCascade.errors`）

**应对**: 
- 使用线程安全的数据结构（`queue.Queue`, `threading.Lock`）
- 每个并行任务使用独立的 `PipelineContext` 副本

### 风险2: 批内质量损失

**描述**: 批大小过大导致角色语气割裂

**应对**:
- 从保守批大小（2）起步
- 设定质量红线（术语不一致率 > 5% → 降低批大小）
- 保留串行模式作为回退选项

### 风险3: 记忆更新顺序错误

**描述**: 批内页面的记忆更新顺序被打乱

**应对**:
- 批内记忆更新强制串行化（按 `page_id` 排序）
- 单元测试覆盖记忆更新时间顺序

### 风险4: Provider 并发限制

**描述**: OpenAI/Anthropic API有速率限制

**应对**:
- 配置 `max_concurrent_requests`（默认5）
- Provider cascade 支持限流（`RateLimiter`）
- 失败自动重试（指数退避）

---

## 配置接口设计

新增配置项（`config.toml`）:

```toml
[translation]
# 并行模式: "serial" | "semantic-parallel" | "batch-parallel"
parallel_mode = "semantic-parallel"

# 批次调度配置（仅 batch-parallel 模式）
batch_size = 3                    # 每批页数
adaptive_batching = false         # 是否启用自适应批大小

# 并发控制
max_concurrent_requests = 5       # 最大并发LLM请求数
semantic_timeout = 30             # Semantic翻译超时（秒）
persona_timeout = 30              # Persona翻译超时（秒）
```

---

## 成功标准

阶段1视为成功需满足：
- ✅ 10页测试集翻译时间 < 700s
- ✅ 所有单元测试通过
- ✅ 质量与串行版本无差异

阶段2视为成功需满足：
- ✅ 批大小=3时翻译时间 < 450s
- ✅ 术语不一致率 < 5%
- ✅ 人工盲测无明显质量损失

整体项目成功标准：
- ✅ 最终方案翻译时间 < 450s（节约 > 60%）
- ✅ 质量可接受（术语一致性 > 95%，语气连续性 > 90%）
- ✅ 代码可维护（单元测试覆盖率 > 80%）

---

## 时间线

| 阶段 | 工作量 | 开始日期 | 预计完成 |
|------|--------|----------|----------|
| 阶段1 | 1天 | 2026-06-07 | 2026-06-08 |
| 实验验证1 | 0.5天 | 2026-06-08 | 2026-06-08 |
| 阶段2 | 2天 | 2026-06-09 | 2026-06-11 |
| 实验验证2 | 1天 | 2026-06-11 | 2026-06-12 |
| 阶段3（可选） | 1天 | TBD | TBD |

**总工期**: 5-6天

---

## 更新日志

- 2026-06-07: 计划初始化，架构师与用户确认方案
- 2026-06-07: 阶段1架构设计完成，交付给实现者
  - 产出: `docs/architecture/phase1-semantic-parallel.md` (20KB，完整技术设计)
  - 产出: `docs/architecture/phase1-handoff.md` (交付清单)
  - 产出: `docs/experiments/phase1-test-plan.md` (实验验证计划)
- 2026-06-07: 阶段1实现完成
  - 代码: ParallelExecutor、TranslationStage扩展、ProviderCascade线程安全
  - 测试: 720个测试全部通过（609现有 + 11新增）
  - 修复: 7个问题（5个中等 + 2个关键）全部解决
  - 审计: 最终裁决 PASS（4个次要建议，不阻塞）
  - 产出: `experiments/run-phase1-tests.sh` (自动化实验脚本)
  - 产出: `experiments/phase1-results.md` (实验报告模板)
- 阶段1实验验证: 待执行（实验员）
- 阶段1完成: 待验证通过后
