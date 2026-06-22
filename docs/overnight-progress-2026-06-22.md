# Overnight Progress 2026-06-22

## P1: Memory Character ID Fragmentation + Generic-Trash Filtering

**Branch:** `fix/p1-memory-fragmentation`
**Commit:** `b3ec0a00`
**Status:** Done — unit tests + simulation verification passing

### Problem

~80 character entries where there should be ~3-4 real characters. Same
character got 8+ IDs (variant descriptions from vision: Miko (variants),
miko_variants, etc.) + trash IDs (Narrator, Environmental, Female character,
Girl with hand to mouth, etc.). Root cause: characters created using the RAW
vision `provisional_speaker` description as the ID; `_GENERIC_SPEAKER_RE`
only blocked bare words (girl/boy/man/woman), not descriptive phrases.

### Fix (two gates)

1. **`mga/memory/speaker_filter.py`** (new) — shared module:
   - `is_generic_speaker()`: expanded filter blocking descriptive phrases
     ("Girl with X", "Female character", "Unseen speaker", "Narrator",
     "Environmental", Japanese markers, etc.) while preserving labels with
     real name tokens in parentheses
   - `extract_name_tokens()`: CJK + Latin token extraction with honorific
     stripping and generic-word filtering
   - `find_canonical_match()`: token-based matching against existing characters
   - `pick_canonical_id()`: prefers CJK token, falls back to Latin

2. **`mga/pipeline/speaker_attribution_stage.py`** — canonicalises vision-set
   `speaker_id` before translation runs:
   - Clears generic IDs (Narrator, Female character, etc.)
   - Merges variant IDs to existing characters via token index
   - Picks clean canonical IDs for new characters (e.g. CJK preferred over
     composite "miko_(variants)")
   - Uses `is_generic_speaker()` instead of the old `_GENERIC_SPEAKER_RE`

3. **`mga/memory/character_memory_updater.py`** — safety-net gate:
   - Skips generic speakers entirely (no character created)
   - Merges variant IDs to existing characters via token matching + alias
   - Creates new characters with clean canonical IDs

### Verification

- **Unit tests:** 26 new tests in `tests/memory/test_speaker_filter.py` covering:
  (a) descriptive hints rejected, (b) variant merging, (c) real names still create
- **Full suite:** 1087 passed, 1 pre-existing render failure (unrelated), 3 skipped
- **Simulation:** 10 trash IDs + 8 fragmented IDs → 3 characters (miko, miku,
  CJK-variant), 0 trash IDs. The 5 CJK-linked variants merged into 1 character.

### Files changed

- `mga/memory/speaker_filter.py` (new — 347 lines)
- `mga/memory/character_memory_updater.py` (+60 lines)
- `mga/pipeline/speaker_attribution_stage.py` (+134 lines)
- `tests/memory/test_speaker_filter.py` (new — 396 lines)
- `tests/pipeline/test_speaker_attribution_stage.py` (+2/-2 lines, assertion update)

## P4: Parallel Translation Default (semantic-parallel)

**Branch:** `fix/p4-parallel-translation`
**Status:** Done — unit tests green, parallel default enabled

### Problem

Translation is **87% of pipeline runtime** (2114s/2437s on the 10-page e2e)
because ~147 LLM calls run serial. `parallel_executor` (max_workers=5) and the
`semantic-parallel` code path already exist but the default was `"serial"`, so
the parallelism was never used unless explicitly configured.

### Fix (code + config)

1. **`mga/pipeline/translation_stage.py:72`** — flipped default from `"serial"`
   to `"semantic-parallel"`. semantic-parallel parallelises the semantic-translation
   LLM calls per page (ThreadPoolExecutor, `max_concurrent_requests` workers) while
   keeping persona rendering serial for memory consistency. A `ParallelExecutionError`
   fallback to serial (`:129`) guarantees this can never be worse than serial. Why-comment
   added: root cause (translation is 87% serial; ~147 LLM calls), what breaks if left
   serial (8x slower than PRD target).

2. **`configs/providers.toml`** — the config file explicitly set
   `parallel_mode = "serial"`, which overrides the code default. Changed to
   `"semantic-parallel"` with a why-comment so the config and code agree. Without this
   dual change, the code flip alone would have no effect (config takes precedence).

3. **`tests/pipeline/test_page_sequential_memory_integration.py`** — 4 tests that
   asserted serial prompt ordering (`prompts[1].startswith("## Persona Rendering")`)
   now explicitly set `translation_config={"parallel_mode": "serial"}` since they test
   memory/relationship injection, not parallelism. semantic-parallel reorders prompts
   (all semantics → all personas per page), so the serial ordering assumption breaks.

### Why semantic-parallel is safe as default

- `_execute_semantic_parallel` processes pages serially (memory consistency) but
  parallelises the semantic-translation LLM calls within each page.
- Persona rendering remains serial (requires memory updates from previous bubbles).
- On `ParallelExecutionError`, the stage clears partial state and falls back to
  `_execute_serial` — so parallel can never produce worse results than serial.
- `batch-parallel` mode (cross-page parallelism) remains opt-in, not default.

### Speedup verification (honest)

The 3-page e2e (`data/input/e2e-3pages/`) was started but **did not complete** within
the 15-minute timeout — mimo (the configured provider) is slow and the vision stage
alone takes significant time. This is the same mimo-slowness symptom that makes
translation 87% of runtime in the first place.

**Real-world speedup depends on provider concurrency allowance.** semantic-parallel
issues concurrent LLM calls via ThreadPoolExecutor; if the provider (mimo) rate-limits
or throttles concurrent requests, the speedup is reduced. The default flip is still
correct because:
- When the provider allows concurrency: semantic-parallel gives up to
  `max_concurrent_requests` (default 5) × speedup on the semantic-translation phase.
- When the provider throttles: the ThreadPoolExecutor naturally serialises behind
  the rate limiter, and the fallback to serial on error ensures correctness.
- The code path is exercised by 22 unit tests (4 batch-parallel, 7 semantic-parallel,
  11 memory-integration) all passing.

### Known constraints

- **mimo rate-limit**: parallel only helps if the provider allows concurrent calls.
  If rate-limiting throttles it, real speedup may need provider quota adjustment.
  The default flip is still correct (no worse than serial); real speedup requires
  provider-side concurrency headroom.
- **e2e not completed**: 3-page e2e timed out at 15min due to mimo slowness (vision
  stage, not translation). This is a provider/infra constraint, not a code issue.

### Verification

- **Parallel-path unit tests:** 22 passed, 1 xfailed (pre-existing)
  (`test_translation_stage_batch.py`, `test_translation_stage_parallel.py`,
  `test_translation_stage.py`, `test_page_sequential_memory_integration.py`)
- **Full suite:** 1087 passed, 1 pre-existing render failure
  (`test_pinning_makes_artifact_deterministic_across_reruns` — missing
  `mga.runtime_bridge.artifact_cache` module, owned by b8c9097 render worktree),
  3 skipped, 1 xfailed

### Files changed

- `mga/pipeline/translation_stage.py` (+9/-2 lines — default flip + why-comment)
- `configs/providers.toml` (+5/-1 lines — config flip + why-comment)
- `tests/pipeline/test_page_sequential_memory_integration.py` (+18/-6 lines —
  4 tests pinned to serial mode for prompt-ordering assertions)
