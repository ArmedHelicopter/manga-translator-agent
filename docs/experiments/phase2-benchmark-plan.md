# Phase 2 Benchmark Plan: Semantic-Parallel & Batch-Parallel Performance Validation

> Date: 2026-06-12
> Status: Ready for execution
> Prerequisite: Phase 1 semantic-parallel implementation complete (845+ tests pass)

---

## 1. Objective

Quantitatively validate the performance gains of semantic-parallel (Phase 1) and batch-parallel (Phase 2) translation modes against the sequential baseline, while confirming that translation quality remains within acceptable bounds.

---

## 2. Test Corpus Requirements

### 2.1 Standard Test Set

| Property | Requirement | Rationale |
|----------|-------------|-----------|
| Page count | 10 pages | Matches original 1073s baseline measurement |
| Character count | ≥ 3 speaking characters | Tests memory accumulation across pages |
| Katakana density | ≥ 2 loanwords per page | Tests term consistency across batches |
| Emotional arc | ≥ 1 emotional shift | Tests persona memory continuity at batch boundaries |
| Format | PNG or PDF, 800×1200+ | Standard manga resolution |

### 2.2 Extended Test Set (Optional)

- 30-page chapter for batch-size tuning at scale
- Multi-chapter volume for incremental mode validation

### 2.3 Corpus Location

Place test images in `data/benchmark/` with the following structure:

```
data/benchmark/
├── standard/          # 10-page test set
│   ├── page_001.png
│   ├── ...
│   └── page_010.png
├── extended/          # 30-page test set (optional)
│   └── ...
└── ground_truth/      # Sequential translation output for comparison
    └── ...
```

---

## 3. Baseline Measurement Procedure

### 3.1 Sequential Baseline

Run the pipeline in fully sequential mode (default):

```bash
manga-translate data/benchmark/standard/ -o result/baseline_sequential/
```

Record:
- **Wall-clock time**: Total end-to-end time
- **Per-stage time**: Format → Vision → Character+Culture → Translation → QA → Render → Output
- **API call count**: Total LLM API calls made
- **Token usage**: Prompt + completion tokens per call
- **Peak memory**: RSS (Resident Set Size) during execution

### 3.2 Metrics Collection

```bash
# Use Python's time module and psutil for instrumentation
python -c "
import time, psutil, os
proc = psutil.Process(os.getpid())
start = time.time()
# ... run pipeline ...
elapsed = time.time() - start
print(f'Wall-clock: {elapsed:.1f}s')
print(f'Peak RSS: {proc.memory_info().rss / 1024 / 1024:.0f} MB')
"
```

Alternatively, add `--profile` flag (if implemented) to output per-stage timing to `result/profile.json`.

---

## 4. Benchmark Scenarios

### 4.1 Phase 1: Semantic-Parallel

```bash
# Semantic-parallel mode
manga-translate data/benchmark/standard/ -o result/semantic_parallel/ \
    --parallel-mode semantic-parallel
```

**Expected results** (from PARALLEL_TRANSLATION_PLAN.md):
- Wall-clock: ~650s (39% reduction from 1073s baseline)
- Persona stage: Still sequential
- Semantic stage: Fully parallel per-page
- Quality: Zero risk (persona accumulates memory sequentially)

### 4.2 Phase 2: Batch-Parallel (Multiple Batch Sizes)

```bash
# Batch size = 2
manga-translate data/benchmark/standard/ -o result/batch_2/ \
    --parallel-mode batch-parallel --batch-size 2

# Batch size = 3 (recommended)
manga-translate data/benchmark/standard/ -o result/batch_3/ \
    --parallel-mode batch-parallel --batch-size 3

# Batch size = 5
manga-translate data/benchmark/standard/ -o result/batch_5/ \
    --parallel-mode batch-parallel --batch-size 5
```

**Expected results**:

| Batch Size | Expected Time | Savings | Quality Trade-off |
|-----------|---------------|---------|-------------------|
| 2 | ~600s | 44% | Minimal (2-page rhythm unit) |
| 3 | ~407s | 62% | Acceptable (3-page rhythm unit) ⭐ |
| 5 | ~290s | 73% | Notable (may miss mid-batch shifts) |

### 4.3 Control: Sequential Re-run

```bash
# Re-run sequential for timing consistency
manga-translate data/benchmark/standard/ -o result/baseline_rerun/
```

---

## 5. Metrics

### 5.1 Performance Metrics

| Metric | Unit | Collection Method |
|--------|------|-------------------|
| Wall-clock time | seconds | `time.time()` start/end |
| Per-stage time | seconds | Instrumented pipeline stages |
| Memory (peak RSS) | MB | `psutil.Process.memory_info()` |
| API call count | integer | Provider call counter |
| Token usage (prompt) | tokens | LLM response `usage.prompt_tokens` |
| Token usage (completion) | tokens | LLM response `usage.completion_tokens` |
| Concurrency efficiency | ratio | `ideal_parallel_time / actual_time` |
| Batch overlap ratio | ratio | `intra_batch_pages / total_pages` |

### 5.2 Quality Metrics

| Metric | Method | Acceptable Threshold |
|--------|--------|---------------------|
| Character voice consistency | Compare speech patterns across pages for same character | Same pattern in ≥ 95% of pages |
| Term consistency | Compare translations of same katakana term across pages | Same translation in ≥ 95% of occurrences |
| Memory accumulation | Verify later pages reference earlier character learning | All character evolutions preserved |
| Intra-batch inconsistency | Count term/voice differences within same batch | < 5% of terms differ |
| Human blind test | Side-by-side comparison without labels | No significant quality difference (p > 0.05) |

### 5.3 Regression Metrics

| Metric | Method | Threshold |
|--------|--------|-----------|
| Unit test suite | `pytest tests/ -v` | 845+ pass |
| E2E output diff | Compare translation JSON files | < 10% text differs from sequential |

---

## 6. Measurement Procedure

### Step 1: Generate Ground Truth

```bash
# Run sequential baseline 3 times, take median
for i in 1 2 3; do
    manga-translate data/benchmark/standard/ -o result/baseline_run$i/
done
# Copy median run to ground_truth/
```

### Step 2: Run Each Scenario 3 Times

For each configuration (semantic-parallel, batch-2, batch-3, batch-5):
1. Run 3 times to account for API latency variance
2. Record all metrics per run
3. Compute median and standard deviation

### Step 3: Quality Validation

For each scenario output:
1. Run `diff` on translation JSON against ground truth
2. Extract character profiles and compare with baseline
3. Count term inconsistencies
4. Flag any pages with missing/empty translations

### Step 4: Report Generation

Produce `docs/experiments/phase2-benchmark-results.md` with:
- Performance comparison table (all scenarios)
- Quality comparison table
- Batch-size performance curve
- Recommendation for default batch_size

---

## 7. Expected Results Summary

Based on the parallel translation plan:

```
Scenario              | Wall-clock | Savings | Quality Risk
----------------------|------------|---------|-------------
Sequential (baseline) | ~1073s     | 0%      | None
Semantic-parallel     | ~650s      | 39%     | None
Batch-parallel (bs=2) | ~600s      | 44%     | Minimal
Batch-parallel (bs=3) | ~407s      | 62%     | Acceptable ⭐
Batch-parallel (bs=5) | ~290s      | 73%     | Notable
```

The recommended default is **batch_size=3** as it provides the best speed/quality trade-off:
- 3 pages ≈ 1 manga rhythm unit (setup → development → punchline)
- Batch boundaries naturally align with scene transitions
- 62% time savings with minimal quality impact

---

## 8. Environment Requirements

- Python 3.12
- All mga dependencies installed (`pip install -e ".[dev]"`)
- LLM API key configured (OpenAI or equivalent)
- `psutil` installed for memory profiling
- Sufficient disk space for result artifacts (~500 MB per run)

---

## 9. Appendix: Automated Benchmark Script

```bash
#!/bin/bash
# run_benchmark.sh — Automated Phase 2 benchmark runner
set -euo pipefail

CORPUS="data/benchmark/standard"
RUNS=3

echo "=== Phase 2 Benchmark ==="
echo "Corpus: $CORPUS"
echo "Runs per scenario: $RUNS"

# Sequential baseline
for i in $(seq 1 $RUNS); do
    echo ">>> Sequential baseline run $i"
    time manga-translate "$CORPUS" -o "result/baseline_run$i/"
done

# Semantic-parallel
for i in $(seq 1 $RUNS); do
    echo ">>> Semantic-parallel run $i"
    time manga-translate "$CORPUS" -o "result/semantic_run$i/" --parallel-mode semantic-parallel
done

# Batch-parallel (batch sizes 2, 3, 5)
for bs in 2 3 5; do
    for i in $(seq 1 $RUNS); do
        echo ">>> Batch-parallel (bs=$bs) run $i"
        time manga-translate "$CORPUS" -o "result/batch${bs}_run$i/" \
            --parallel-mode batch-parallel --batch-size "$bs"
    done
done

echo "=== Benchmark complete ==="
echo "Results in: result/*/"
```
