#!/usr/bin/env bash
# 全量端到端翻译测试脚本
# 用途：翻译 ./data/input/*.pdf，输出到 ./data/output/，使用 mimo-v2.5-pro 模型
# 包含：翻译 + wiki + RAG + 术语库 + 角色档案等所有产物

set -e  # 遇到错误立即退出

# 配置
INPUT_DIR="./data/input"
OUTPUT_BASE="./data/output"
CONFIG="./configs/providers.toml"
LANG="ja-zh"  # 日语到中文
PROVIDER="mimo"
MODEL="mimo-v2.5-pro"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查环境
check_environment() {
    log_info "检查环境..."
    
    # 检查 manga-translate 命令
    if ! command -v manga-translate &> /dev/null; then
        log_error "manga-translate 命令不存在，请先安装：pip install -e ."
        exit 1
    fi
    
    # 检查输入目录
    if [ ! -d "$INPUT_DIR" ]; then
        log_error "输入目录不存在：$INPUT_DIR"
        exit 1
    fi
    
    # 检查 PDF 文件
    PDF_COUNT=$(find "$INPUT_DIR" -maxdepth 1 -name "*.pdf" | wc -l)
    if [ "$PDF_COUNT" -eq 0 ]; then
        log_error "在 $INPUT_DIR 中没有找到 PDF 文件"
        exit 1
    fi
    
    log_info "找到 $PDF_COUNT 个 PDF 文件"
    
    # 检查配置文件
    if [ ! -f "$CONFIG" ]; then
        log_error "配置文件不存在：$CONFIG"
        exit 1
    fi
    
    # 检查 API key
    if [ -z "$MIMO_API_KEY" ]; then
        log_warn "环境变量 MIMO_API_KEY 未设置"
        log_warn "如果配置文件中没有硬编码 API key，翻译会失败"
    fi
    
    log_info "环境检查完成"
}

# 翻译单个 PDF
translate_pdf() {
    local input_pdf="$1"
    local basename=$(basename "$input_pdf" .pdf)
    local output_dir="$OUTPUT_BASE/$basename"
    
    log_info "开始翻译：$basename"
    
    # 创建输出目录（作为项目目录，包含 memory/ 等）
    mkdir -p "$output_dir"
    
    # 初始化项目 memory 结构
    log_info "  初始化 memory 结构..."
    manga-translate memory init "$output_dir" || log_warn "  memory init 失败（可能已存在）"
    
    # 运行翻译
    log_info "  执行翻译管道..."
    manga-translate translate "$input_pdf" \
        -o "$output_dir/translated" \
        --provider "$PROVIDER" \
        --config "$CONFIG" \
        --lang "$LANG" \
        --save-json \
        2>&1 | tee "$output_dir/translation.log"
    translate_status=${PIPESTATUS[0]}
    
    if [ "$translate_status" -eq 0 ]; then
        log_info "  ✅ 翻译成功：$basename"
        
        # 检查产物
        log_info "  检查产物..."
        
        if [ -d "$output_dir/translated" ]; then
            TRANSLATED_COUNT=$(find "$output_dir/translated" -name "*.png" -o -name "*.jpg" | wc -l)
            log_info "    - 翻译图片：$TRANSLATED_COUNT 个"
        fi
        
        if [ -d "$output_dir/memory" ]; then
            CHAR_COUNT=$(find "$output_dir/memory/characters" -name "*.md" 2>/dev/null | wc -l)
            TERM_COUNT=$(find "$output_dir/memory/terms" -name "*.md" 2>/dev/null | wc -l)
            log_info "    - 角色档案：$CHAR_COUNT 个"
            log_info "    - 术语条目：$TERM_COUNT 个"
        fi
        
        if [ -f "$output_dir/translated/manifest.json" ]; then
            log_info "    - manifest.json：✅"
        fi
        
        if [ -f "$output_dir/translated/run.json" ]; then
            log_info "    - run.json：✅"
        fi
        
        return 0
    else
        log_error "  ❌ 翻译失败：$basename"
        return 1
    fi
}

# 主函数
main() {
    log_info "=========================================="
    log_info "Manga Translate Agent - 全量翻译测试"
    log_info "=========================================="
    log_info ""
    log_info "配置："
    log_info "  输入目录：$INPUT_DIR"
    log_info "  输出目录：$OUTPUT_BASE"
    log_info "  配置文件：$CONFIG"
    log_info "  Provider：$PROVIDER"
    log_info "  模型：$MODEL"
    log_info "  语言对：$LANG"
    log_info ""
    
    check_environment
    
    # 创建输出基础目录
    mkdir -p "$OUTPUT_BASE"
    
    # 统计
    local total=0
    local success=0
    local failed=0
    
    # 遍历所有 PDF
    for pdf in "$INPUT_DIR"/*.pdf; do
        if [ -f "$pdf" ]; then
            ((total++))
            if translate_pdf "$pdf"; then
                ((success++))
            else
                ((failed++))
            fi
            log_info ""
        fi
    done
    
    # 总结
    log_info "=========================================="
    log_info "翻译完成"
    log_info "=========================================="
    log_info "总计：$total 个文件"
    log_info "成功：$success 个"
    log_info "失败：$failed 个"
    log_info ""
    log_info "产物位置："
    log_info "  $OUTPUT_BASE/"
    log_info "    ├── <文件名1>/"
    log_info "    │   ├── translated/          # 翻译后的图片"
    log_info "    │   ├── memory/              # wiki + RAG 产物"
    log_info "    │   │   ├── characters/      # 角色档案 (Markdown)"
    log_info "    │   │   ├── terms/           # 术语库 (Markdown)"
    log_info "    │   │   ├── scenes/          # 场景记录"
    log_info "    │   │   └── state/           # JSON 状态 (canonical)"
    log_info "    │   └── translation.log      # 翻译日志"
    log_info "    └── <文件名2>/"
    log_info ""
    
    if [ "$failed" -gt 0 ]; then
        log_warn "有 $failed 个文件翻译失败，请检查日志"
        exit 1
    fi
    
    log_info "✅ 全部翻译成功！"
}

# 运行
main "$@"
