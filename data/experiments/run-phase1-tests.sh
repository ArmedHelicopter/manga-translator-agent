#!/bin/bash
# Phase 1 实验执行脚本
# 用途：自动运行所有实验并生成报告

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "========================================="
echo "阶段1实验：Semantic 并行翻译验证"
echo "========================================="
echo ""

# 检查测试数据
if [ ! -d "data/experiments/phase1-test-set" ]; then
    echo -e "${YELLOW}警告: 测试集不存在，请先准备测试数据${NC}"
    echo "建议: 从 data/input/*.pdf 抽取 10 页到 data/experiments/phase1-test-set/"
    echo ""
    echo "示例:"
    echo "  mkdir -p data/experiments/phase1-test-set"
    echo "  # 使用 PDF 工具抽取前 10 页"
    exit 1
fi

# 创建输出目录
mkdir -p output/{baseline,parallel,timeout-test,stability-test-{1,2,3}}
mkdir -p logs
mkdir -p experiments

echo "[准备] 输出目录已创建"
echo ""

# ===== 实验1: 性能基准测试 =====
echo "========================================="
echo "实验1: 性能基准测试"
echo "========================================="

echo -e "${GREEN}[1/2] 运行串行模式（baseline）...${NC}"
START_BASELINE=$(date +%s)
manga-translate data/experiments/phase1-test-set/ \
  -o output/baseline/ \
  --config configs/phase1-experiment.toml \
  --log-level INFO 2>&1 | tee logs/baseline.log
END_BASELINE=$(date +%s)
BASELINE_TIME=$((END_BASELINE - START_BASELINE))
echo -e "${GREEN}串行模式完成: ${BASELINE_TIME}s${NC}"
echo ""

echo -e "${GREEN}[2/2] 运行 Semantic 并行模式...${NC}"
START_PARALLEL=$(date +%s)
manga-translate data/experiments/phase1-test-set/ \
  -o output/parallel/ \
  --config configs/phase1-experiment.toml \
  --parallel semantic \
  --max-concurrent-requests 5 \
  --log-level INFO 2>&1 | tee logs/parallel.log
END_PARALLEL=$(date +%s)
PARALLEL_TIME=$((END_PARALLEL - START_PARALLEL))
echo -e "${GREEN}并行模式完成: ${PARALLEL_TIME}s${NC}"
echo ""

# 计算加速比
if [ $BASELINE_TIME -gt 0 ]; then
    SPEEDUP=$(echo "scale=2; $BASELINE_TIME / $PARALLEL_TIME" | bc)
    SAVING=$(echo "scale=1; (1 - $PARALLEL_TIME / $BASELINE_TIME) * 100" | bc)
    echo "性能对比:"
    echo "  串行: ${BASELINE_TIME}s"
    echo "  并行: ${PARALLEL_TIME}s"
    echo "  加速比: ${SPEEDUP}x"
    echo "  节约: ${SAVING}%"
else
    echo -e "${RED}错误: 串行基线测试失败${NC}"
fi
echo ""

# ===== 实验2: 质量对比 =====
echo "========================================="
echo "实验2: 翻译质量对比"
echo "========================================="

if [ -f "output/baseline/manifest.json" ] && [ -f "output/parallel/manifest.json" ]; then
    echo "对比翻译输出..."
    
    # 简单对比（完整对比脚本需要 Python）
    BASELINE_BUBBLES=$(jq '.pages[].bubbles | length' output/baseline/manifest.json | awk '{s+=$1} END {print s}')
    PARALLEL_BUBBLES=$(jq '.pages[].bubbles | length' output/parallel/manifest.json | awk '{s+=$1} END {print s}')
    
    echo "  气泡数量 - 串行: ${BASELINE_BUBBLES}, 并行: ${PARALLEL_BUBBLES}"
    
    if [ "$BASELINE_BUBBLES" = "$PARALLEL_BUBBLES" ]; then
        echo -e "  ${GREEN}✓ 气泡数量一致${NC}"
    else
        echo -e "  ${RED}✗ 气泡数量不一致${NC}"
    fi
    
    # 记忆状态对比
    if [ -d "output/baseline/memory/state" ] && [ -d "output/parallel/memory/state" ]; then
        echo "  对比记忆状态..."
        DIFF_COUNT=$(diff -r output/baseline/memory/state/ output/parallel/memory/state/ 2>/dev/null | wc -l || echo "0")
        
        if [ "$DIFF_COUNT" = "0" ]; then
            echo -e "  ${GREEN}✓ 记忆状态完全一致${NC}"
        else
            echo -e "  ${YELLOW}! 记忆状态有差异（$DIFF_COUNT 行）${NC}"
        fi
    fi
else
    echo -e "${RED}错误: 输出文件不存在，跳过质量对比${NC}"
fi
echo ""

# ===== 实验3: 超时降级测试 =====
echo "========================================="
echo "实验3: 错误处理验证"
echo "========================================="

echo "测试超时降级（semantic_timeout=1）..."
TRANSLATION_PARALLEL_MODE=semantic-parallel \
TRANSLATION_SEMANTIC_TIMEOUT=1 \
manga-translate data/experiments/phase1-test-set/ \
  -o output/timeout-test/ \
  --config configs/phase1-experiment.toml \
  --log-level DEBUG 2>&1 | tee logs/timeout-test.log || true

# 检查降级日志
if grep -q "falling back to serial" logs/timeout-test.log; then
    echo -e "${GREEN}✓ 检测到超时降级${NC}"
else
    echo -e "${YELLOW}! 未检测到降级日志（可能未超时）${NC}"
fi
echo ""

# ===== 实验4: 稳定性测试 =====
echo "========================================="
echo "实验4: 并发安全性测试"
echo "========================================="

echo "运行3次重复测试..."
for i in {1..3}; do
    echo -e "${GREEN}[${i}/3] 运行稳定性测试...${NC}"
    manga-translate data/experiments/phase1-test-set/ \
      -o output/stability-test-$i/ \
      --config configs/phase1-experiment.toml \
      --parallel semantic \
      --log-level WARNING 2>&1 | tee logs/stability-$i.log
done

echo "对比3次运行结果..."
DIFF_12=$(diff output/stability-test-1/manifest.json output/stability-test-2/manifest.json 2>/dev/null | wc -l || echo "999")
DIFF_23=$(diff output/stability-test-2/manifest.json output/stability-test-3/manifest.json 2>/dev/null | wc -l || echo "999")

if [ "$DIFF_12" = "0" ] && [ "$DIFF_23" = "0" ]; then
    echo -e "${GREEN}✓ 3次运行结果完全一致${NC}"
else
    echo -e "${YELLOW}! 运行结果有差异（可能是时间戳或随机性）${NC}"
fi
echo ""

# ===== 生成报告摘要 =====
echo "========================================="
echo "实验完成摘要"
echo "========================================="
echo ""
echo "性能:"
echo "  串行: ${BASELINE_TIME}s"
echo "  并行: ${PARALLEL_TIME}s"
echo "  加速: ${SPEEDUP}x (节约 ${SAVING}%)"
echo ""
echo "验收标准:"
if [ "$PARALLEL_TIME" -lt 700 ] && [ "$BASELINE_TIME" -gt 1000 ]; then
    echo -e "  ${GREEN}✓ 性能目标达成（< 700s）${NC}"
else
    echo -e "  ${YELLOW}! 性能待验证（目标: < 700s）${NC}"
fi
echo ""
echo "详细结果已保存到:"
echo "  - logs/baseline.log (串行日志)"
echo "  - logs/parallel.log (并行日志)"
echo "  - logs/timeout-test.log (降级测试)"
echo "  - logs/stability-*.log (稳定性测试)"
echo ""
echo "下一步: 手动审查 experiments/phase1-results.md 并填写实验数据"
echo ""
