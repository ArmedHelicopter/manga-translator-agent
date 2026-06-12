# 阶段1实验结果：Semantic 并行翻译验证

**实验日期**: 2026-06-07  
**实验员**: 待执行  
**状态**: 🟡 等待实验数据

---

## 执行摘要

⏳ **实验状态**: 准备就绪，等待实验员执行

**测试数据**: `data/input/私を喰べたい、ひとでなし(8).pdf` (130MB)

**实验目标**:
- 验证 Semantic 并行模式的实际性能收益
- 确认翻译质量与串行模式一致
- 测试错误处理和降级机制

---

## 实验1: 性能基准测试

### 测试步骤

```bash
# 1. 准备测试集（抽取10页）
mkdir -p data/experiments/phase1-test-set
# 从 PDF 抽取页面 1-10 到测试目录

# 2. 串行基线（baseline）
manga-translate data/experiments/phase1-test-set/ \
  -o output/baseline/ \
  --config configs/phase1-experiment.toml \
  --log-level INFO

# 3. Semantic 并行模式
manga-translate data/experiments/phase1-test-set/ \
  -o output/parallel/ \
  --config configs/phase1-experiment.toml \
  --parallel semantic \
  --max-concurrent-requests 5 \
  --log-level INFO
```

### 数据收集模板

| 指标 | 串行模式 | Semantic并行 | 提升 |
|------|----------|--------------|------|
| 总时间 (s) | ___ | ___ | ___% |
| Translation阶段 (s) | ___ | ___ | ___% |
| - Semantic (s) | ___ | ___ | ___% |
| - Persona (s) | ___ | ___ | ___% |
| - Memory更新 (s) | ___ | ___ | ___% |
| Vision阶段 (s) | ___ | ___ | - |
| QA阶段 (s) | ___ | ___ | - |
| Render阶段 (s) | ___ | ___ | - |
| **Semantic加速比** | 1.0x | ___x | - |
| **并发效率 (%)** | - | ___% | - |

**并发效率计算**: `实际加速比 / 理论加速比 (5x)`

### 预期结果

- ✅ 总时间节约 > 35%（1073s → < 700s）
- ✅ Semantic 阶段加速比 3.5-4.5x
- ✅ 并发效率 > 70%

### 实际结果

⏳ 待执行

---

## 实验2: 翻译质量对比

### 测试步骤

```bash
# 提取翻译文本
python << 'EOF'
import json
from pathlib import Path

def extract_translations(manifest_path):
    with open(manifest_path, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    translations = []
    for page in manifest.get('pages', []):
        for bubble in page.get('bubbles', []):
            translations.append({
                'bubble_id': bubble.get('bubble_id'),
                'text': bubble.get('translation', {}).get('text', '')
            })
    return translations

baseline = extract_translations('output/baseline/manifest.json')
parallel = extract_translations('output/parallel/manifest.json')

# 对比
matches = sum(1 for b, p in zip(baseline, parallel) if b['text'] == p['text'])
total = len(baseline)
print(f"文本一致性: {matches}/{total} ({matches/total*100:.2f}%)")

# 输出差异
for b, p in zip(baseline, parallel):
    if b['text'] != p['text']:
        print(f"\n差异 - {b['bubble_id']}:")
        print(f"  串行: {b['text']}")
        print(f"  并行: {p['text']}")
EOF
```

### 记忆状态对比

```bash
# 对比角色档案
diff -u \
  output/baseline/memory/state/character_*.json \
  output/parallel/memory/state/character_*.json
```

### 数据收集

| 指标 | 结果 | 说明 |
|------|------|------|
| 文本一致性 (%) | ___% | 完全相同的气泡百分比 |
| 记忆状态一致性 | ✅/❌ | JSON diff是否为空 |
| 术语一致性问题 | ___ | 不一致案例数 |
| 角色语气一致性 | ✅/❌ | 人工盲测结果 |

### 预期结果

- ✅ 文本一致性 > 99%
- ✅ 记忆状态完全一致（diff 为空）
- ✅ 术语一致性问题 = 0

### 实际结果

⏳ 待执行

---

## 实验3: 错误处理验证

### 测试3.1: Provider 超时降级

```bash
# 修改配置强制超时
cat > configs/phase1-timeout-test.toml << 'EOF'
[translation]
parallel_mode = "semantic-parallel"
max_concurrent_requests = 5
semantic_timeout = 1  # 1秒必定超时

[llm]
primary_provider = "openai"
primary_model = "gpt-4o-mini"
EOF

# 运行并观察降级
manga-translate data/experiments/phase1-test-set/ \
  -o output/timeout-test/ \
  --config configs/phase1-timeout-test.toml \
  --log-level DEBUG 2>&1 | tee logs/timeout-test.log

# 验证日志中包含:
# - "ParallelExecutionError"
# - "falling back to serial mode"
```

### 测试3.2: Provider 部分失败

（需要 monkeypatch，可选实验）

### 数据收集

| 场景 | 预期行为 | 实际行为 | 状态 |
|------|----------|----------|------|
| Semantic 超时 | 自动降级到串行 | ___ | ✅/❌ |
| Provider 失败 | 记录错误，降级 | ___ | ✅/❌ |
| 网络不稳定 | 重试或降级 | ___ | ✅/❌ |

### 预期结果

- ✅ 超时后自动降级，日志包含 "falling back to serial"
- ✅ 降级后翻译成功完成
- ✅ 无崩溃或数据损坏

### 实际结果

⏳ 待执行

---

## 实验4: 并发安全性测试

### 测试步骤

```bash
# 重复运行3次
for i in {1..3}; do
  echo "=== Run $i ==="
  manga-translate data/experiments/phase1-test-set/ \
    -o output/stability-test-$i/ \
    --parallel semantic \
    --log-level INFO
  
  # 记录运行时间
  echo "Run $i completed"
done

# 对比3次运行的输出
diff -u output/stability-test-1/manifest.json output/stability-test-2/manifest.json
diff -u output/stability-test-2/manifest.json output/stability-test-3/manifest.json
```

### 资源监控

```bash
# 监控内存和线程（运行期间）
watch -n 1 'ps aux | grep manga-translate | grep -v grep'
```

### 数据收集

| 指标 | 运行1 | 运行2 | 运行3 | 一致性 |
|------|-------|-------|-------|--------|
| 总时间 (s) | ___ | ___ | ___ | ___% |
| 翻译文本 | ___ | ___ | ___ | ✅/❌ |
| 记忆状态 | ___ | ___ | ___ | ✅/❌ |
| 进程峰值内存 (MB) | ___ | ___ | ___ | - |

### 预期结果

- ✅ 3次运行全部成功
- ✅ 翻译结果完全一致
- ✅ 无内存泄漏或线程泄漏

### 实际结果

⏳ 待执行

---

## 问题清单

### P0: 阻塞问题（必须修复）

_暂无_

### P1: 性能问题（影响验收）

_待实验数据_

### P2: 质量问题（需要评估）

_待实验数据_

### P3: 改进建议（可延后）

_待实验数据_

---

## 环境信息

### 硬件
- CPU: ___
- 内存: ___
- 网络: ___

### 软件
- Python: `python --version`
- 依赖: `pip list | grep -E "(openai|anthropic|requests)"`
- Provider: OpenAI (gpt-4o-mini)
- API 配额: ___

### 配置
```bash
cat configs/phase1-experiment.toml
```

---

## 结论与建议

### 性能验收

- [ ] 总时间 < 700s（节约 > 35%）
- [ ] Semantic 加速比 > 3.0x
- [ ] 并发效率 > 70%

### 质量验收

- [ ] 文本一致性 > 99%
- [ ] 记忆状态一致
- [ ] 无术语不一致

### 稳定性验收

- [ ] 3次重复运行无失败
- [ ] 无资源泄漏
- [ ] 错误降级正常工作

### 最终推荐

⏳ **待实验完成后评估**

- [ ] ✅ 通过验收，推荐进入阶段2
- [ ] ⚠️ 部分通过，需修复问题后重测
- [ ] ❌ 未通过验收，需重新设计

---

## 实验员签名

**执行人**: ___  
**执行日期**: ___  
**审核人**: 架构师  
**审核日期**: ___

---

## 附录：快速执行脚本

```bash
#!/bin/bash
# experiments/run-phase1-tests.sh

set -e

echo "=== Phase 1 Experiments ==="

# 创建输出目录
mkdir -p output/{baseline,parallel,timeout-test,stability-test-{1,2,3}}
mkdir -p logs

# 实验1: 性能基准
echo "[1/4] Running baseline (serial mode)..."
time manga-translate data/experiments/phase1-test-set/ \
  -o output/baseline/ \
  --mode serial 2>&1 | tee logs/baseline.log

echo "[1/4] Running semantic-parallel mode..."
time manga-translate data/experiments/phase1-test-set/ \
  -o output/parallel/ \
  --parallel semantic 2>&1 | tee logs/parallel.log

# 实验2: 质量对比
echo "[2/4] Comparing quality..."
python experiments/compare_outputs.py \
  output/baseline/manifest.json \
  output/parallel/manifest.json \
  > logs/quality-comparison.txt

# 实验3: 超时测试
echo "[3/4] Testing timeout fallback..."
TRANSLATION_PARALLEL_MODE=semantic-parallel \
TRANSLATION_SEMANTIC_TIMEOUT=1 \
manga-translate data/experiments/phase1-test-set/ \
  -o output/timeout-test/ 2>&1 | tee logs/timeout-test.log

# 实验4: 稳定性测试
echo "[4/4] Stability test (3 runs)..."
for i in {1..3}; do
  echo "  Run $i/3..."
  manga-translate data/experiments/phase1-test-set/ \
    -o output/stability-test-$i/ \
    --parallel semantic 2>&1 | tee logs/stability-$i.log
done

echo "=== All experiments completed ==="
echo "Results saved to experiments/phase1-results.md"
```

使用方法:
```bash
chmod +x experiments/run-phase1-tests.sh
./experiments/run-phase1-tests.sh
```
