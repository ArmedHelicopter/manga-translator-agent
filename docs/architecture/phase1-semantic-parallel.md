# 阶段1架构设计：Semantic 并行翻译

## 概述

**目标**: 将 Semantic 翻译（事实层）并行化，保持 Persona 翻译（语气层）串行，验证并行基础设施。

**预期收益**: 1073s → ~650s（节约 39%）

**风险等级**: 低（Persona 仍依赖实时记忆，质量零风险）

---

## 当前架构分析

### 现有翻译流程（串行）

```python
# mga/pipeline/translation_stage.py::_translate_page()

for bubble in page.bubbles:
    # 1. Semantic 翻译（事实层）~60-70% 时间
    semantic = call_semantic_llm(bubble.source_text)
    
    # 2. Persona 翻译（语气层）~30-40% 时间
    persona = call_persona_llm(
        semantic, 
        memory=char_mem  # 依赖累积记忆
    )
    
    # 3. 记忆更新（轻量）
    memory_updater.update_from_translation(bubble, persona)
```

**时间分解（10页，50个气泡）**:
- Semantic: 50 × 15s = 750s
- Persona: 50 × 5s = 250s
- 记忆更新: 50 × 0.5s = 25s
- 其他（QA、渲染）: ~50s
- **总计**: ~1073s

### 依赖关系图

```
Bubble1.semantic ────────→ Bubble1.persona ──→ Memory₁
                                ↓
Bubble2.semantic ────────→ Bubble2.persona ──→ Memory₂
                           (读取 Memory₁)      ↓
Bubble3.semantic ────────→ Bubble3.persona ──→ Memory₃
                           (读取 Memory₂)
```

**关键洞察**:
- Semantic 翻译**不依赖**记忆（只依赖术语DB、场景上下文）
- Persona 翻译**强依赖**记忆（语气、口癖、关系语气）
- 记忆更新**必须串行**（保持时间顺序）

---

## 新架构设计

### 两阶段并行模式

```python
# 阶段1: 批量并行 Semantic（快）
semantics = parallel_map(
    bubbles, 
    func=call_semantic_llm,
    max_workers=5
)

# 阶段2: 串行 Persona + 记忆更新（中速）
for bubble, semantic in zip(bubbles, semantics):
    persona = call_persona_llm(semantic, memory=current_memory)
    current_memory = update_memory(bubble, persona)
```

**时间计算**:
- Semantic 并行: 750s ÷ 5 = 150s
- Persona 串行: 250s
- 记忆更新: 25s
- 其他: 50s
- **新总计**: ~475s（实际考虑并发开销 ~650s）

### 模块结构

```
mga/pipeline/
├── parallel_executor.py          # 新增：并行调度器
│   ├── ParallelExecutor          # 抽象调度器
│   ├── ThreadPoolExecutor        # 线程池实现
│   └── ProcessPoolExecutor       # 进程池实现（未来）
│
├── translation_stage.py          # 修改：支持并行模式
│   ├── _translate_page()         # 调度入口
│   ├── _translate_page_serial()  # 串行实现（保留）
│   └── _translate_page_semantic_parallel()  # 新增：并行实现
```

---

## 核心组件设计

### 1. ParallelExecutor（并行调度器）

```python
# mga/pipeline/parallel_executor.py

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, TypeVar, Dict, Any

T = TypeVar('T')
R = TypeVar('R')

class ParallelExecutor:
    """Thread-safe parallel executor for LLM calls."""
    
    def __init__(self, max_workers: int = 5, timeout: int = 60):
        self.max_workers = max_workers
        self.timeout = timeout
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
    
    def map(
        self, 
        items: List[T], 
        func: Callable[[T], R],
        context: Dict[str, Any] = None
    ) -> List[R]:
        """
        并行执行函数，保持输入顺序。
        
        Args:
            items: 输入项列表
            func: 处理函数（必须线程安全）
            context: 共享只读上下文（如 config, provider）
        
        Returns:
            结果列表（与输入顺序一致）
        
        Raises:
            ParallelExecutionError: 如果任何任务失败
        """
        futures = {}
        results = [None] * len(items)
        
        # 提交任务
        for idx, item in enumerate(items):
            future = self._executor.submit(func, item, context)
            futures[future] = idx
        
        # 收集结果（保持顺序）
        errors = []
        for future in as_completed(futures, timeout=self.timeout):
            idx = futures[future]
            try:
                results[idx] = future.result()
            except Exception as exc:
                errors.append((idx, exc))
        
        if errors:
            raise ParallelExecutionError(
                f"{len(errors)} tasks failed", 
                errors=errors
            )
        
        return results
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self._executor.shutdown(wait=True)


class ParallelExecutionError(Exception):
    """并行执行失败异常"""
    def __init__(self, message: str, errors: List[tuple]):
        super().__init__(message)
        self.errors = errors  # [(idx, exception), ...]
```

**设计要点**:
- 使用 `ThreadPoolExecutor`（GIL 影响小，主要是网络IO）
- 保持输入输出顺序（`results[idx]`）
- 超时控制（防止某个请求卡住整个批次）
- 错误聚合（收集所有失败任务）

### 2. TranslationStage 修改

```python
# mga/pipeline/translation_stage.py

class TranslationStage(PipelineStage):
    def execute(self, context: PipelineContext) -> PipelineContext:
        cfg = context.project_config
        parallel_mode = cfg.translation.get("parallel_mode", "serial")
        
        if parallel_mode == "semantic-parallel":
            return self._execute_semantic_parallel(context)
        else:
            return self._execute_serial(context)  # 现有逻辑
    
    def _execute_serial(self, context: PipelineContext) -> PipelineContext:
        """现有串行实现（重命名，逻辑不变）"""
        # ... 现有 execute() 的代码 ...
    
    def _execute_semantic_parallel(self, context: PipelineContext) -> PipelineContext:
        """新增：Semantic 并行，Persona 串行"""
        cfg = context.project_config
        max_workers = cfg.translation.get("max_concurrent_requests", 5)
        
        provider_cascade = ProviderCascade(cfg, "translation")
        cultural_adapter = CulturalAdapter(...)
        memory_updater = CharacterMemoryUpdater(...)
        
        all_translations = []
        realization_traces = []
        
        for page_index, page in enumerate(context.pages):
            # 阶段1: 并行 Semantic
            semantics = self._parallel_semantic_translation(
                page=page,
                context=context,
                provider_cascade=provider_cascade,
                cultural_adapter=cultural_adapter,
                max_workers=max_workers
            )
            
            # 阶段2: 串行 Persona + 记忆更新
            page_translations, page_traces = self._serial_persona_rendering(
                page=page,
                semantics=semantics,
                context=context,
                provider_cascade=provider_cascade,
                memory_updater=memory_updater
            )
            
            all_translations.extend(page_translations)
            realization_traces.extend(page_traces)
            
            # 刷新下一页的记忆
            self._refresh_page_profiles_after_memory_update(...)
        
        context.translations = all_translations
        context.artifacts[self.name] = {...}
        return context
    
    def _parallel_semantic_translation(
        self, 
        page, 
        context, 
        provider_cascade,
        cultural_adapter,
        max_workers
    ) -> List[SemanticTranslation]:
        """并行翻译页内所有气泡的 Semantic 层"""
        
        def translate_one_bubble(bubble, shared_ctx):
            """线程安全的 Semantic 翻译函数"""
            cult_page = shared_ctx["cultural_context"].get(page.page_id, {})
            vision_ctx = self._build_vision_context(page, bubble)
            translation_memory = MemoryRetrieval.search_translation_memory(...)
            
            prompt = _build_semantic_translation_prompt(
                bubble.source_text, 
                cult_page, 
                shared_ctx["target_lang"],
                vision_ctx=vision_ctx,
                translation_memory=translation_memory
            )
            
            # 注意：每个线程使用独立的 provider 实例副本
            provider = shared_ctx["provider_cascade"].clone()
            raw, _ = provider.call_chat(
                [{"role": "user", "content": prompt}],
                operation="semantic_translation"
            )
            
            semantic = self._parse_semantic_response(bubble.bubble_id, raw)
            semantic.footnotes = self._ensure_katakana_footnotes(
                source_text=bubble.source_text,
                translated_text=semantic.text,
                footnotes=semantic.footnotes
            )
            return semantic
        
        shared_context = {
            "target_lang": context.project_config.target_lang,
            "cultural_context": context.cultural_context,
            "provider_cascade": provider_cascade
        }
        
        with ParallelExecutor(max_workers=max_workers) as executor:
            semantics = executor.map(
                page.bubbles, 
                translate_one_bubble,
                context=shared_context
            )
        
        return semantics
    
    def _serial_persona_rendering(
        self,
        page,
        semantics: List[SemanticTranslation],
        context,
        provider_cascade,
        memory_updater
    ) -> Tuple[List[TranslationCandidate], List[DialogueRealizationTrace]]:
        """串行渲染 Persona 层（依赖实时记忆）"""
        
        results = []
        traces = []
        page_profiles = context.memory_context.get("page_profiles", {})
        mem_page = page_profiles.get(page.page_id, {})
        
        for bubble, semantic in zip(page.bubbles, semantics):
            speaker = bubble.speaker_id or ""
            char_mem = mem_page.get(speaker, {})
            
            # 构建 Persona prompt
            vision_ctx = self._build_vision_context(page, bubble)
            relationship_ctx, listener = self._build_relationship_context(...)
            
            persona_prompt = _build_persona_render_prompt(
                bubble.source_text,
                semantic,
                char_mem,
                context.project_config.target_lang,
                relationship_ctx=relationship_ctx,
                vision_ctx=vision_ctx,
                listener_id=listener,
                ...
            )
            
            # 调用 Persona LLM
            candidate, persona, _ = self._call_persona_llm(
                provider_cascade=provider_cascade,
                bubble_id=bubble.bubble_id,
                prompt=persona_prompt,
                semantic=semantic,
                speaker_id=speaker or None,
                listener_id=listener,
                ...
            )
            
            # 文化适配 + 术语归一化
            candidate.text = cultural_adapter.process_translation(...)
            candidate.text = self._normalize_name_translation(...)
            
            # 记忆更新（串行，保持顺序）
            if speaker and memory_updater is not None:
                update = memory_updater.update_from_translation(
                    speaker=speaker,
                    bubble=bubble,
                    page_id=page.page_id,
                    translated_text=candidate.text,
                    memory_before=char_mem,
                    prompt=persona_prompt
                )
                # 更新到全局记忆（下一个气泡可见）
                context.memory_context["character_profiles"][speaker] = update.memory_after
                mem_page[speaker] = update.memory_after
            
            results.append(candidate)
            traces.append(DialogueRealizationTrace(...))
        
        return results, traces
```

**设计要点**:
- `_parallel_semantic_translation()`: 独立函数，易于单元测试
- `translate_one_bubble()`: 闭包函数，访问只读上下文
- `provider_cascade.clone()`: 每个线程独立的 provider 实例（避免状态污染）
- `_serial_persona_rendering()`: 保持现有逻辑，确保记忆顺序

---

## 线程安全性分析

### 需要保护的共享状态

| 对象 | 访问模式 | 线程安全性 | 应对措施 |
|------|----------|-----------|----------|
| `ProviderCascade` | 读写（记录errors） | ❌ 不安全 | 每线程 clone() |
| `PipelineContext` | 读写 | ❌ 不安全 | Semantic 阶段只读，Persona 阶段单线程 |
| `CulturalAdapter` | 读（terminology_db） | ✅ 安全 | 只读访问 |
| `MemoryRetrieval` | 读 | ✅ 安全 | 只读访问 |
| `MemoryUpdater` | 写 | ❌ 不安全 | 仅在 Persona 串行阶段使用 |

### ProviderCascade 线程安全改造

```python
# mga/providers/cascade.py

class ProviderCascade:
    def __init__(self, config: ProjectConfig, stage: str):
        self.config = config
        self.stage = stage
        self.errors: List[Dict] = []  # 非线程安全
        self._lock = threading.Lock()  # 新增：保护 errors
    
    def clone(self) -> "ProviderCascade":
        """创建独立副本（独立的 errors 列表）"""
        instance = ProviderCascade.__new__(ProviderCascade)
        instance.config = self.config
        instance.stage = self.stage
        instance.errors = []  # 独立的错误列表
        instance._lock = threading.Lock()
        return instance
    
    def call_chat(self, messages, operation, trace_context=None):
        try:
            # ... 现有逻辑 ...
        except Exception as exc:
            with self._lock:  # 保护写操作
                self.errors.append({
                    "operation": operation,
                    "error": str(exc)
                })
            raise
```

---

## 配置接口

### config.toml 新增配置

```toml
[translation]
# 并行模式: "serial" | "semantic-parallel"
parallel_mode = "serial"  # 默认串行（兼容现有行为）

# 并发控制（仅 semantic-parallel 模式生效）
max_concurrent_requests = 5  # 最大并发 LLM 请求数
semantic_timeout = 60        # Semantic 翻译超时（秒）

# Provider 限流（防止触发 API 速率限制）
rate_limit_rpm = 100         # 每分钟最大请求数（可选）
```

### 运行时切换

```bash
# 串行模式（现有行为）
manga-translate input.pdf -o output/ 

# Semantic 并行模式
manga-translate input.pdf -o output/ --parallel semantic

# 通过环境变量
TRANSLATION_PARALLEL_MODE=semantic-parallel manga-translate input.pdf -o output/
```

---

## 测试策略

### 单元测试

```python
# tests/pipeline/test_parallel_executor.py

def test_parallel_executor_preserves_order():
    """测试并行执行保持输入顺序"""
    def square(x, ctx):
        return x * x
    
    executor = ParallelExecutor(max_workers=3)
    results = executor.map([1, 2, 3, 4, 5], square)
    
    assert results == [1, 4, 9, 16, 25]


def test_parallel_executor_handles_errors():
    """测试错误聚合"""
    def fail_on_even(x, ctx):
        if x % 2 == 0:
            raise ValueError(f"Even number: {x}")
        return x
    
    executor = ParallelExecutor(max_workers=2)
    
    with pytest.raises(ParallelExecutionError) as exc_info:
        executor.map([1, 2, 3, 4], fail_on_even)
    
    assert len(exc_info.value.errors) == 2  # 2 和 4 失败


def test_parallel_executor_timeout():
    """测试超时控制"""
    def slow_func(x, ctx):
        import time
        time.sleep(10)
        return x
    
    executor = ParallelExecutor(max_workers=2, timeout=2)
    
    with pytest.raises(ParallelExecutionError):
        executor.map([1, 2], slow_func)
```

```python
# tests/pipeline/test_translation_stage_parallel.py

def test_semantic_parallel_mode_produces_same_output(monkeypatch):
    """测试 Semantic 并行模式与串行模式输出一致"""
    # Setup
    config = ProjectConfig(...)
    config.translation["parallel_mode"] = "semantic-parallel"
    context = build_test_context()
    
    stage = TranslationStage()
    parallel_result = stage.execute(context)
    
    # 对比串行模式
    config.translation["parallel_mode"] = "serial"
    context_serial = build_test_context()
    serial_result = stage.execute(context_serial)
    
    # 断言：翻译文本一致
    assert parallel_result.translations == serial_result.translations
    
    # 断言：记忆更新一致
    assert parallel_result.memory_context == serial_result.memory_context


def test_semantic_parallel_thread_safety(monkeypatch):
    """测试并发安全性（无竞态条件）"""
    # 模拟 provider 调用
    call_count = {"count": 0}
    lock = threading.Lock()
    
    def mock_call_chat(messages, operation, trace_context):
        with lock:
            call_count["count"] += 1
        return '{"text": "测试", "confidence": 0.9}', None
    
    monkeypatch.setattr(ProviderCascade, "call_chat", mock_call_chat)
    
    # 执行
    stage = TranslationStage()
    context = build_test_context(num_bubbles=20)
    stage._execute_semantic_parallel(context)
    
    # 验证所有调用都被执行
    assert call_count["count"] == 20
```

### 集成测试

```python
# tests/integration/test_e2e_parallel.py

def test_end_to_end_parallel_translation():
    """端到端测试：10页漫画 Semantic 并行翻译"""
    input_pdf = "tests/fixtures/test-10pages.pdf"
    output_dir = tempfile.mkdtemp()
    
    config = ProjectConfig.load("tests/fixtures/config-parallel.toml")
    
    orchestrator = PipelineOrchestrator(config=config)
    context = orchestrator.run(input_pdf, output_dir, config)
    
    # 验证输出
    assert len(context.translations) > 0
    assert len(context.errors) == 0
    assert context.metadata["total_duration"] < 700  # 性能要求
    
    # 验证质量（与基线对比）
    baseline = load_baseline_translations("tests/fixtures/baseline-10pages.json")
    assert translation_similarity(context.translations, baseline) > 0.95
```

### 性能基准测试

```python
# tests/benchmarks/bench_parallel.py

import pytest

@pytest.mark.benchmark
def test_benchmark_serial_vs_parallel(benchmark):
    """基准测试：串行 vs Semantic 并行"""
    
    def run_translation(mode):
        config = ProjectConfig(...)
        config.translation["parallel_mode"] = mode
        orchestrator = PipelineOrchestrator(config=config)
        orchestrator.run("tests/fixtures/test-10pages.pdf", "/tmp/output", config)
    
    # 串行基线
    baseline = benchmark(run_translation, "serial")
    print(f"Serial: {baseline}s")
    
    # Semantic 并行
    parallel = benchmark(run_translation, "semantic-parallel")
    print(f"Parallel: {parallel}s")
    
    # 断言：并行至少快 30%
    assert parallel < baseline * 0.7
```

---

## 错误处理与降级

### 并行失败降级策略

```python
class TranslationStage(PipelineStage):
    def _execute_semantic_parallel(self, context: PipelineContext):
        try:
            # 尝试并行执行
            return self._parallel_semantic_translation(...)
        except ParallelExecutionError as exc:
            logger.warning(
                f"Parallel semantic translation failed ({len(exc.errors)} errors), "
                f"falling back to serial mode"
            )
            # 自动降级到串行模式
            return self._execute_serial(context)
        except TimeoutError:
            logger.error("Parallel execution timeout, falling back to serial mode")
            return self._execute_serial(context)
```

### Provider 错误聚合

```python
class TranslationStage(PipelineStage):
    def execute(self, context: PipelineContext):
        # ... 执行翻译 ...
        
        # 收集所有 provider 错误（包括并行线程的）
        if parallel_mode == "semantic-parallel":
            all_provider_errors = self._collect_parallel_provider_errors()
            context.artifacts[self.name]["provider_cascade_errors"] = all_provider_errors
```

---

## 性能优化建议

### 1. Provider 连接池

```python
# mga/providers/base.py

class LLMProvider:
    def __init__(self, config):
        # 复用 HTTP 连接（requests.Session）
        self.session = requests.Session()
        self.session.mount('https://', HTTPAdapter(pool_maxsize=10))
```

### 2. Semantic 结果缓存

```python
# mga/pipeline/translation_stage.py

_SEMANTIC_CACHE: Dict[str, SemanticTranslation] = {}

def _call_semantic_llm_cached(self, bubble_id, source_text, prompt):
    cache_key = hashlib.md5(prompt.encode()).hexdigest()
    
    if cache_key in _SEMANTIC_CACHE:
        logger.debug(f"Semantic cache hit: {bubble_id}")
        return _SEMANTIC_CACHE[cache_key]
    
    semantic = self._call_semantic_llm(bubble_id, prompt)
    _SEMANTIC_CACHE[cache_key] = semantic
    return semantic
```

### 3. 批量 Provider 调用

```python
# 未来优化：支持批量 API（如 OpenAI Batch API）
class ProviderCascade:
    def call_chat_batch(self, requests: List[Dict]) -> List[str]:
        """批量调用（如果 provider 支持）"""
        if self.primary_provider.supports_batch:
            return self.primary_provider.batch_complete(requests)
        else:
            # 降级到逐个调用
            return [self.call_chat(req["messages"]) for req in requests]
```

---

## 交付清单

### 代码文件

- [x] `docs/architecture/phase1-semantic-parallel.md`（本文档）
- [ ] `mga/pipeline/parallel_executor.py`（并行调度器）
- [ ] `mga/pipeline/translation_stage.py`（修改：支持并行模式）
- [ ] `mga/providers/cascade.py`（修改：线程安全改造）
- [ ] `mga/config/loader.py`（修改：新增并行配置）

### 测试文件

- [ ] `tests/pipeline/test_parallel_executor.py`（单元测试）
- [ ] `tests/pipeline/test_translation_stage_parallel.py`（单元测试）
- [ ] `tests/integration/test_e2e_parallel.py`（集成测试）
- [ ] `tests/benchmarks/bench_parallel.py`（性能基准）

### 文档

- [ ] `experiments/phase1-test-plan.md`（实验计划）
- [ ] `experiments/phase1-results.md`（实验结果，由实验员产出）
- [ ] `PARALLEL_TRANSLATION_PLAN.md`（更新状态为"阶段1完成"）

---

## 验收标准

### 功能验收

- [ ] 串行模式(`parallel_mode=serial`)行为与现有版本完全一致
- [ ] Semantic 并行模式可通过配置开关启用
- [ ] 所有 609 个单元测试通过
- [ ] 新增测试覆盖率 > 85%

### 性能验收

- [ ] 10页测试集翻译时间 < 700s
- [ ] 并发效率 > 70%（实际加速 ÷ 理论加速）
- [ ] 无死锁或竞态条件

### 质量验收

- [ ] 翻译文本与串行版本一致性 > 99%
- [ ] 记忆更新顺序正确（后续气泡看到前序气泡的记忆）
- [ ] 无 Provider 调用丢失或重复

---

## 下一步

阶段1完成后：
1. 实验员运行性能基准测试，产出 `experiments/phase1-results.md`
2. 根据实验结果决定是否进入阶段2（分批递推并行）
3. 更新 `PARALLEL_TRANSLATION_PLAN.md` 状态为"✅ 阶段1完成"
