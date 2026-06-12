# 测试规范和常见陷阱

## 问题记录：递归输入导致重复处理

### 问题描述
**日期：** 2026-06-09  
**发现者：** 用户  
**严重性：** 高 - 导致测试时间 10 倍膨胀

### 症状
- 10 页输入目录被处理成 89 张图片
- Pass 1 用了 57.5 分钟而不是预期的 5-10 分钟
- 出现多次重复运行（parallel-run-1, 2, 3...）
- 日志显示 "Translated 89 images" 而不是 10

### 根本原因
输入目录 `./data/experiments/phase1-test-set/` 包含了**之前运行的输出子目录**：
```
./data/experiments/phase1-test-set/
├── page-001.png          ← 原始输入
├── page-002.png          ← 原始输入
├── ...
├── .mga-payload/         ← 之前的 payload（包含 64 个 PNG）
├── output/               ← 之前的输出
├── memory/               ← 之前的记忆
└── cache/                ← 之前的缓存
```

CLI 递归扫描时找到了所有子目录中的图片，导致重复处理。

### 解决方案

#### 🔴 强制规范：测试前清理

```bash
# 错误做法 ❌
manga-translate translate ./data/experiments/phase1-test-set/ -o output/

# 正确做法 ✅
# 1. 创建干净的输入目录
mkdir -p ./data/input/test-clean
cp ./data/experiments/phase1-test-set/page-*.png ./data/input/test-clean/

# 2. 清理之前的输出
rm -rf ./data/output/test-result

# 3. 运行翻译
manga-translate translate ./data/input/test-clean/ -o ./data/output/test-result
```

### 标准测试流程

#### 1. 准备干净输入
```bash
# 总是从源文件创建新的输入目录
mkdir -p ./data/input/test-{name}
cp {source}/*.png ./data/input/test-{name}/

# 验证文件数
ls ./data/input/test-{name}/*.png | wc -l
```

#### 2. 清理输出目录
```bash
# 删除之前的输出（避免污染）
rm -rf ./data/output/test-{name}
```

#### 3. 设置环境变量
```bash
# 确保 API key 正确加载
export $(grep -v '^#' .env | grep -v '^$' | xargs) 2>/dev/null
echo "MIMO_API_KEY length: ${#MIMO_API_KEY}"
```

#### 4. 运行测试
```bash
# 使用干净的输入和输出路径
manga-translate translate ./data/input/test-{name}/ \
  -o ./data/output/test-{name} \
  --mode manga \
  2>&1 | tee ./data/output/test-{name}.log
```

#### 5. 验证结果
```bash
# 检查输出文件数
ls ./data/output/test-{name}/*.png | wc -l

# 检查日志中的处理数量
grep "Translated.*images" ./data/output/test-{name}.log
```

### 目录结构规范

```
project/
├── data/
│   ├── input/              ← 干净的测试输入（临时）
│   │   ├── test-1-page/
│   │   ├── test-3-pages/
│   │   └── test-10-pages/
│   ├── output/             ← 测试输出（临时）
│   │   ├── test-1-page/
│   │   ├── test-3-pages/
│   │   └── test-10-pages/
│   └── experiments/        ← 原始数据（只读，不直接用作输入）
│       └── phase1-test-set/
```

### 检查清单

测试前必须检查：
- [ ] 输入目录只包含 PNG 文件，无子目录
- [ ] 输入文件数 = 预期数量（`ls *.png | wc -l`）
- [ ] 输出目录不存在或已清空
- [ ] 环境变量已正确设置（`echo ${#MIMO_API_KEY}`）
- [ ] 日志文件路径正确（避免覆盖）

### 相关问题

**问题 #2：环境变量未传递**
- 症状：`No provider available for stage 'translation'`
- 解决：显式 export API key，不依赖自动加载
- 验证：`echo ${#MIMO_API_KEY}` 应显示 51

**问题 #3：LLM 返回 list 而非 string**
- 症状：`Input should be a valid string [type=string_type, input_value=[...], input_type=list]`
- 解决：添加 `@field_validator` 使用 `_coerce_str`
- 位置：`mga/models/translation.py` - `SemanticTranslation` 类

### 更新记录

| 日期 | 更新内容 |
|------|----------|
| 2026-06-09 | 初始版本 - 记录递归输入问题 |
| 2026-06-09 | 添加环境变量和 list coercion 问题 |

---

**重要：** 每次测试前必须遵循此规范，避免浪费时间和 API 配额。