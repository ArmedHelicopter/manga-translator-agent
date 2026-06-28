# Experiment #12: optimize-translation-pipeline-bcdf

## Problem Statement

Current pipeline processes 28 bubbles in ~16 minutes. Target: 2-3 minutes.

**Root causes:**
1. Translation stage runs pages sequentially (`for page in context.pages`)
2. Per-bubble concurrency capped at `min(3, len(bubbles))` — hardcoded
3. No LLM response caching — identical source text re-translates every run
4. No pipeline overlap — vision must complete for ALL pages before translation starts

## Design: 3 Parallel Modes

### Mode 1: `serial` (current default)
- Pages processed sequentially
- Bubbles within a page: up to 3 concurrent via ThreadPoolExecutor
- No caching
- Backward compatible, no behavior change

### Mode 2: `parallel`
- Pages processed concurrently (configurable `pipeline_concurrency`, default 5)
- Bubbles within a page: same as serial (up to 3 concurrent)
- LLM cache enabled (SQLite)
- Memory updater uses lock for thread-safe character state updates

### Mode 3: `pipelined`
- Pages stream through stages asynchronously
- asyncio event loop manages page flow
- ThreadPoolExecutor handles blocking LLM calls
- Stage N for page K runs concurrently with stage N+1 for page K-1
- Full LLM cache enabled
- Most complex, highest throughput

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  ProjectConfig                       │
│  pipeline_mode: "manga" | "novel"                    │
│  parallel_mode: "serial" | "parallel" | "pipelined"  │
│  pipeline_concurrency: int = 5                       │
│  llm_cache_enabled: bool = True                      │
│  llm_cache_dir: str = ".mga_cache"                   │
└─────────────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────┐
│              PipelineOrchestrator                     │
│  .run() → dispatches to:                             │
│    _run_serial()     ← current behavior              │
│    _run_parallel()   ← ThreadPoolExecutor per stage  │
│    _run_pipelined()  ← asyncio event loop            │
└─────────────────────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  LLM Cache   │ │ ParallelExec │ │  Memory Lock  │
│  (SQLite)    │ │ (configurable│ │  (threading   │
│  key: hash   │ │  max_workers)│ │   .Lock)      │
└──────────────┘ └──────────────┘ └──────────────┘
```

## Implementation Plan

### Phase 1: Config + Cache (Foundation)

**1.1 Extend ProjectConfig** (`mga/models/project.py`)
```python
parallel_mode: str = "serial"  # serial | parallel | pipelined
pipeline_concurrency: int = 5  # max pages in flight
llm_cache_enabled: bool = True
llm_cache_dir: str = ".mga_cache"
translation_max_workers: int = 3  # per-page bubble concurrency
```

**1.2 SQLite LLM Cache** (`mga/cache/llm_cache.py`)
- Table: `llm_responses(hash TEXT PK, response TEXT, provider TEXT, model TEXT, created_at TIMESTAMP)`
- Key: SHA256(source_text + stage + target_lang + model + prompt_version)
- `get(prompt_key) -> str | None`
- `put(prompt_key, response, provider, model)`
- Thread-safe: sqlite3 in WAL mode, single connection per thread via threading.local()

### Phase 2: Parallel Pages

**2.1 TranslationStage._translate_pages_parallel()**
- Use ThreadPoolExecutor(max_workers=config.pipeline_concurrency)
- Each page is a unit of work
- Memory updater uses threading.Lock for character state updates
- Results collected in order

**2.2 Cache integration in translation_stage.py**
- Before LLM call: check cache
- After LLM call: store in cache
- Cache key includes prompt hash (semantic vs persona)

### Phase 3: Pipelined Execution

**3.1 PipelineOrchestrator._run_pipelined()**
```python
async def _run_pipelined(self, context):
    # Create queues between stages
    page_stream = asyncio.Queue(maxsize=concurrency)
    
    # Producer: feed pages
    async def feed_pages():
        for page in context.pages:
            await page_stream.put(page)
    
    # Each stage is a transformer
    async def run_stage(stage, input_q, output_q):
        while True:
            page = await input_q.get()
            page_ctx = make_single_page_context(context, page)
            result = await asyncio.get_event_loop().run_in_executor(
                executor, stage.execute, page_ctx
            )
            await output_q.put(result)
    
    # Pipeline: stage1_q -> stage1 -> stage2_q -> stage2 -> ...
```

**3.2 Thread pool management**
- Single shared ThreadPoolExecutor(max_workers=pipeline_concurrency)
- Passed to async stages via context
- Shutdown on orchestrator cleanup

### Phase 4: Local Model Compatibility

**4.1 Provider-aware concurrency**
- Local providers (ollama, vllm, lmstudio): use `local_max_workers` (default: num_cores)
- Remote providers: use `pipeline_concurrency` (default: 5)
- Config in provider_settings

## Files to Modify

| File | Change |
|------|--------|
| `mga/models/project.py` | Add parallel_mode, pipeline_concurrency, llm_cache_enabled, llm_cache_dir, translation_max_workers |
| `mga/pipeline/orchestrator.py` | Add _run_parallel(), _run_pipelined() dispatch |
| `mga/pipeline/translation_stage.py` | Use configurable max_workers, integrate cache |
| `mga/pipeline/parallel_executor.py` | Add config-driven max_workers |
| `mga/config/loader.py` | Parse new config fields from TOML |
| `mga/pipeline/stages.py` | Add cache and thread_pool to PipelineContext |

## Files to Create

| File | Purpose |
|------|---------|
| `mga/cache/__init__.py` | Cache module init |
| `mga/cache/llm_cache.py` | SQLite-backed LLM response cache |
| `tests/pipeline/test_parallel_modes.py` | Test serial/parallel/pipelined modes |
| `tests/cache/test_llm_cache.py` | Test cache hit/miss/eviction |

## Verification Plan

1. **Unit tests**: Cache CRUD, parallel executor with mock LLM, pipeline mode dispatch
2. **Integration test**: 3 high-res manga pages, measure:
   - Serial baseline
   - Parallel (concurrency=5)
   - Pipelined (concurrency=5)
3. **Correctness**: Compare translation output between modes (should be identical with cache disabled)
4. **Performance target**: 28 bubbles / 3 pages in < 3 minutes with pipelined mode

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Memory updater race condition | threading.Lock around character state updates |
| SQLite write contention | WAL mode + batch inserts |
| Async complexity | Start with parallel mode, pipelined as stretch goal |
| Breaking existing behavior | serial mode is default, zero behavior change |
| Thread pool lifecycle | Explicit shutdown in orchestrator.__del__ or context manager |

## Execution Order

1. Phase 1: Config + Cache (can test independently)
2. Phase 2: Parallel pages (biggest impact, moderate complexity)
3. Phase 4: Local model compat (config changes only)
4. Phase 3: Pipelined (stretch goal, highest complexity)
