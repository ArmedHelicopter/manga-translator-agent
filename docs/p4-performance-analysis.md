# P4 Performance Analysis — translation is 87% of runtime

> Bottleneck data + optimization directions. Produced 2026-06-22 during overnight PRD advance.

## Data (10-page e2e, 2026-06-19, total ~2437s)

From `data/output/test-pdf-10pages/metadata/run.json` → `stage_timings`:

| Stage | Time (s) | Share |
|---|---|---|
| **translation** | **2114.5** | **86.8%** |
| vision | 185.7 | 7.6% |
| qa | 70.1 | 2.9% |
| render | 56.0 | 2.3% |
| character / speaker / format / ocr | ~0 | — |

**Translation is the bottleneck.** Everything else is <10% combined. PRD target <30s/page (300s/10pp) is unreachable without attacking translation.

## Why translation is slow

`provider_cascade_calls` shows ~147 LLM calls for 70 translations:
- 70 × `semantic_translation` + 70 × `persona_render` = 140 (two calls per bubble)
- + 7 × `qa_retranslate`
- ~147 calls × ~14.4s avg = 2114s, **serial**.

`mga/pipeline/parallel_executor.py` exists (ThreadPoolExecutor, max_workers=5) but `translation` ran serial — parallel mode (semantic-parallel / batch-parallel, "done" per DELIVERY_SUMMARY) is **not the default**.

## Optimization directions (ranked)

1. **Enable parallel translation by default.** parallel_executor (5 workers) on ~147 calls → ~30 effective × 14s ≈ 420s. That alone takes 10pp from 2437s → ~750s (75s/page). Biggest win, lowest risk (code exists).
2. **Merge persona_render into semantic_translation** — two calls/bubble → one. Halves translation calls. Bigger change (prompt/schema merge).
3. **LLM cache reuse** — `.mga_cache/llm_cache.db` exists; ensure re-runs skip unchanged bubbles (artifact pin already helps).
4. **Model routing** — persona_render to a faster model; keep semantic on the strong one.

## Acceptance for P4

- 10-page e2e < 5 min (from 40 min). Per-page < 30s aspirational (needs 1+2+3).
- No regression in translation quality (vision-e2e: rendered text still correct).

## ⚠️ Parallel speedup UNVERIFIED on high-concurrency providers (2026-06-23 update)

P4's default was flipped to `semantic-parallel`, then **reverted to `serial`** after testing: the only configured provider (**mimo token-plan**) has a low concurrency limit — `max_concurrent_requests=5` exceeds it, concurrent calls fail with `"No provider available for stage 'translation'. Tried: ['mimo']"`, burn the 60s `semantic_timeout`, then fall back to serial anyway. Running serial by default avoids the wasted timeout every page.

**The ~5x speedup estimate is THEORETICAL, never measured.** It's based on `max_concurrent_requests=5` vs serial arithmetic. Real-world speedup requires a provider that actually allows concurrent calls (OpenAI / Gemini / etc.), and **no such provider has been tested** — mimo is the only one configured, and it throttles concurrency. The `semantic-parallel` code path itself is exercised by 22 unit tests (so it doesn't crash), but end-to-end acceleration on a high-concurrency provider is **unverified**.

To actually verify: configure a high-concurrency provider in `configs/providers.toml` → set `parallel_mode = "semantic-parallel"` → run e2e → compare `stage_timings.translation` vs the serial baseline (2114s/10pp). Until that's done, P4's perf gain is aspirational, not demonstrated.

## Constraints

- `translation_stage.py` is being modified by P1 (memory gate, agent 93779b93) right now — **do not touch it in parallel**. P4 should change `parallel_mode` default at the **config/orchestrator layer**, or land after P1 merges.
- Persona-merge (direction 2) touches translation_stage internals → sequence after P1.
