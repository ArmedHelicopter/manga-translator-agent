# 阶段1交付清单：Semantic 并行翻译

## 交付给 /full-flow 的完整包

本文档是架构师向实现者（/full-flow 或下游工程师）交付阶段1的完整规格。

---

## 📋 架构文档（已完成）

- ✅ `PARALLEL_TRANSLATION_PLAN.md` - 总体计划（3阶段路线图）
- ✅ `docs/architecture/phase1-semantic-parallel.md` - 详细架构设计
- ✅ `docs/experiments/phase1-test-plan.md` - 实验验证计划

---

## 🎯 实现目标

**核心目标**: 将 Semantic 翻译并行化，保持 Persona 串行，验证并行基础设施

**性能目标**: 1073s → ~650s（节约 39%）

**质量要求**: 翻译结果与串行模式完全一致（文本一致性 > 99%）

---

## 📦 需要创建的代码模块

### 1. 并行调度器
**文件**: `mga/pipeline/parallel_executor.py`

**功能**:
- `ParallelExecutor` 类：线程池并行执行
- `map()` 方法：并行映射函数，保持输入顺序
- `ParallelExecutionError` 异常：聚合失败任务

**接口**:
```python
class ParallelExecutor:
    def __init__(self, max_workers: int = 5, timeout: int = 60):
        ...
    
    def map(
        self, 
        items: List[T], 
        func: Callable[[T, Dict], R],
        context: Dict[str, Any] = None
    ) -> List[R]:
        """
        并行执行 func，保持输入顺序。
        context 是只读共享上下文。
        抛出 ParallelExecutionError 如果任何任务失败。
        """
        ...
```

**关键要求**:
- 使用 `concurrent.futures.ThreadPoolExecutor`
- 保证输出顺序与输入一致
- 超时控制（防止卡住）
- 错误聚合（收集所有失败任务的异常）

---

### 2. TranslationStage 扩展
**文件**: `mga/pipeline/translation_stage.py`（修改现有文件）

**新增方法**:
- `_execute_semantic_parallel()` - Semantic并行 + Persona串行的主流程
- `_parallel_semantic_translation()` - 页内气泡的批量 Semantic 翻译
- `_serial_persona_rendering()` - 串行 Persona 渲染 + 记忆更新

**修改方法**:
- `execute()` - 根据 `config.translation.parallel_mode` 路由到不同实现
- 重命名现有 `execute()` 逻辑为 `_execute_serial()`（保持兼容）

**关键要求**:
- Semantic 阶段每个线程使用独立的 `ProviderCascade.clone()`
- Persona 阶段严格串行执行，保证记忆更新顺序
- 错误处理：并行失败时自动降级到串行模式

---

### 3. ProviderCascade 线程安全改造
**文件**: `mga/providers/cascade.py`（修改现有文件）

**新增方法**:
```python
def clone(self) -> "ProviderCascade":
    """创建独立副本（独立的 errors 列表）"""
    ...
```

**修改**:
- 添加 `threading.Lock()` 保护 `self.errors` 列表
- 在 `call_chat()` 的异常处理中使用锁

**关键要求**:
- `clone()` 返回的实例有独立的 `errors` 列表
- 不影响现有串行模式的行为

---

### 4. 配置加载扩展
**文件**: `mga/config/loader.py`（修改现有文件）

**新增配置项**:
```toml
[translation]
parallel_mode = "serial"  # "serial" | "semantic-parallel"
max_concurrent_requests = 5
semantic_timeout = 60
```

**关键要求**:
- 默认值为 `"serial"`（保持现有行为）
- 支持环境变量覆盖：`TRANSLATION_PARALLEL_MODE`

---

## 🧪 需要创建的测试文件

### 1. 单元测试：ParallelExecutor
**文件**: `tests/pipeline/test_parallel_executor.py`

**测试用例**:
- ✅ `test_parallel_executor_preserves_order` - 验证输出顺序
- ✅ `test_parallel_executor_handles_errors` - 验证错误聚合
- ✅ `test_parallel_executor_timeout` - 验证超时控制
- ✅ `test_parallel_executor_thread_safety` - 验证无竞态条件

---

### 2. 单元测试：TranslationStage 并行模式
**文件**: `tests/pipeline/test_translation_stage_parallel.py`

**测试用例**:
- ✅ `test_semantic_parallel_mode_produces_same_output` - 对比串行/并行输出
- ✅ `test_semantic_parallel_thread_safety` - 验证并发安全
- ✅ `test_parallel_falls_back_to_serial_on_error` - 验证降级机制
- ✅ `test_memory_update_order_preserved` - 验证记忆更新顺序

---

### 3. 集成测试：端到端
**文件**: `tests/integration/test_e2e_parallel.py`

**测试用例**:
- ✅ `test_end_to_end_parallel_translation` - 10页完整流程
- ✅ `test_parallel_with_different_providers` - 测试不同 Provider
- ✅ `test_parallel_memory_consistency` - 验证记忆状态一致性

---

### 4. 性能基准测试
**文件**: `tests/benchmarks/bench_parallel.py`

**测试用例**:
- ✅ `test_benchmark_serial_vs_parallel` - 对比性能
- 断言：并行时间 < 串行时间 × 0.7

---

## 📊 实验员任务（不改代码）

实验员从 `./data/input/*.pdf` 抽取10页，运行以下实验：

### 实验1：性能基准测试
```bash
# 串行基线
manga-translate data/experiments/phase1-test-set/ -o data/output/baseline/ --mode serial

# Semantic 并行
manga-translate data/experiments/phase1-test-set/ -o data/output/parallel/ --parallel semantic
```

**记录**: 总时间、各阶段时间、加速比、并发效率

---

### 实验2：质量对比
- 提取翻译文本，逐气泡对比
- 人工盲测（20个气泡）

**记录**: 文本一致性百分比、质量评分

---

### 实验3：记忆一致性
- 对比 `memory/state/character_*.json`
- 检查 `speech_patterns`, `catchphrases`, `tone_spectrum`

**记录**: JSON diff 是否为空

---

### 实验4：并发安全性
- 重复运行10次，检查结果一致性
- 监控内存和线程泄漏

**记录**: 成功率、资源泄漏情况

---

### 实验5：错误处理
- 模拟超时、Provider失败、网络不稳定
- 验证自动降级机制

**记录**: 降级是否正常工作

---

**产出**: `experiments/phase1-results.md`（包含所有实验数据和问题清单）

---

## ✅ 验收标准

阶段1必须满足以下标准才能标记为"完成"：

### 功能验收
- [ ] 串行模式 (`parallel_mode=serial`) 行为不变
- [ ] Semantic 并行模式可通过配置启用
- [ ] 所有 609 个现有单元测试通过
- [ ] 新增测试覆盖率 > 85%

### 性能验收
- [ ] 10页测试集翻译时间 < 700s
- [ ] 并发效率 > 70%
- [ ] 无死锁或超时

### 质量验收
- [ ] 翻译文本一致性 > 99%
- [ ] 记忆状态完全一致（JSON diff 为空）
- [ ] 无 Provider 调用丢失或重复

---

## 🚀 实现顺序建议

建议按以下顺序实现（降低风险）：

1. **实现 ParallelExecutor**（独立模块，易测试）
   - 编写 `parallel_executor.py`
   - 编写单元测试 `test_parallel_executor.py`
   - 运行测试确保通过

2. **改造 ProviderCascade**（小改动，低风险）
   - 添加 `clone()` 方法
   - 添加线程锁保护 `errors`
   - 运行现有 Provider 测试确保兼容

3. **扩展 TranslationStage**（核心逻辑）
   - 实现 `_execute_semantic_parallel()`
   - 实现 `_parallel_semantic_translation()`
   - 实现 `_serial_persona_rendering()`
   - 修改 `execute()` 路由逻辑

4. **编写 TranslationStage 测试**
   - 单元测试对比串行/并行输出
   - 验证记忆更新顺序

5. **集成测试和基准测试**
   - 端到端测试
   - 性能基准测试

6. **配置接口**
   - 扩展 `config/loader.py`
   - 更新默认配置文件

7. **文档和实验**
   - 更新 README（如何启用并行模式）
   - 实验员运行测试计划
   - 产出 `experiments/phase1-results.md`

---

## 📝 完成后的更新

实现者完成所有代码和测试后，实验员完成验证后，架构师需要：

1. 审查代码和测试（Code Review）
2. 确认实验结果符合验收标准
3. 更新 `PARALLEL_TRANSLATION_PLAN.md`:
   ```markdown
   ### 阶段1：Semantic 并行（基础设施） ✅ COMPLETED
   
   **状态**: ✅ 完成于 2026-06-XX
   
   **实际收益**:
   - 时间: 1073s → XXXs（节约 XX%）
   - 质量: 文本一致性 XX%，记忆一致
   
   **关键发现**:
   - ...
   ```

4. 决策是否进入阶段2（分批递推并行）

---

## 📞 联系与支持

- **架构师**: 负责设计决策、实验评审
- **实现者** (/full-flow): 负责代码实现、单元测试
- **实验员**: 负责性能验证、质量测试（不改代码）

如果实现过程中遇到架构问题（如"是否需要进程池而非线程池？"），请联系架构师讨论。

如果实验发现质量问题（如记忆顺序错误），请在 `experiments/phase1-results.md` 详细记录，架构师将评估是否需要调整设计。

---

## 🎁 附录：关键代码示例

详见 `docs/architecture/phase1-semantic-parallel.md` 的以下章节：
- 第3节：核心组件设计（ParallelExecutor 完整实现）
- 第4节：TranslationStage 修改（详细代码）
- 第5节：线程安全性分析
- 第6节：测试策略（完整测试用例）

---

**交付完成日期**: 2026-06-07

**预计实现完成**: 2026-06-08（1个工作日）

**预计验证完成**: 2026-06-08 下午（0.5个工作日）
