# Agent 使用指南 - 如何高效执行翻译测试

> 本文档专门为 AI Agent（Kiro、Claude Code 等）编写，说明如何快速理解和执行用户的翻译测试需求。

---

## 场景识别

当用户说类似：
- "用 ./data/input/*.pdf 跑一次全量日语翻译到中文"
- "翻译这些 PDF 并导出 wiki 和 RAG 产物"
- "测试一下 mimo-v2.5-pro 模型的翻译效果"
- "批量翻译这些文件到 ./data/output/"

**识别为**：端到端翻译测试任务

---

## 快速决策树

```
用户要求翻译测试
    ↓
是否明确指定了输入文件？
    ├─ 是 → 是否是单个文件？
    │        ├─ 是 → 使用命令 A（单文件翻译）
    │        └─ 否 → 使用方案 B（批量翻译脚本）
    └─ 否 → 询问用户输入文件位置
    
是否要求导出 wiki/RAG 产物？
    ├─ 是 → 添加 --save-json 参数
    └─ 否 → 基础翻译即可
    
是否指定了模型/provider？
    ├─ 是 → 使用指定的 provider
    └─ 否 → 默认使用 mimo
```

---

## 标准执行流程

### 步骤 1：理解需求

**必须确认的信息**：
- [ ] 输入文件位置（例如：`./data/input/*.pdf`）
- [ ] 输出目录（例如：`./data/output/`）
- [ ] 模型/provider（例如：`mimo-v2.5-pro`）
- [ ] 语言对（例如：日语→中文）
- [ ] 是否需要完整产物（wiki、RAG、角色档案等）

**缺失信息的默认值**：
- 输入：`./data/input/`
- 输出：`./data/output/`
- Provider：`mimo`
- 语言：`ja-zh`（日→中）
- 完整产物：是（添加 `--save-json`）

---

### 步骤 2：选择执行方式

#### 方案 A：单文件翻译（用户明确指定单个文件）

```bash
manga-translate translate <输入文件> \
  -o <输出目录> \
  --provider <provider名称> \
  --config configs/providers.toml \
  --lang <语言对> \
  --save-json
```

**示例**：
```bash
manga-translate translate data/input/chapter1.pdf \
  -o data/output/chapter1 \
  --provider mimo \
  --config configs/providers.toml \
  --lang ja-zh \
  --save-json
```

#### 方案 B：批量翻译（用户要求翻译多个文件，如 `*.pdf`）

**推荐**：使用现成的测试脚本

```bash
# 确保脚本可执行
chmod +x scripts/test_translate_full.sh

# 运行（会自动翻译 data/input/ 下所有 PDF）
bash scripts/test_translate_full.sh
```

**或者手动循环**：
```bash
for pdf in data/input/*.pdf; do
    basename=$(basename "$pdf" .pdf)
    manga-translate translate "$pdf" \
      -o "data/output/$basename" \
      --provider mimo \
      --config configs/providers.toml \
      --lang ja-zh \
      --save-json
done
```

---

### 步骤 3：检查前置条件

在执行翻译前，**必须检查**：

```bash
# 1. 检查输入目录是否存在
ls data/input/*.pdf 2>/dev/null
# 如果没有找到文件，提示用户

# 2. 检查配置文件是否存在
ls configs/providers.toml
# 如果不存在，提示用户或使用默认配置

# 3. 检查环境变量（如果需要）
echo "MIMO_API_KEY is set: ${MIMO_API_KEY:+yes}"
# 如果未设置且配置文件中也没有硬编码 key，警告用户

# 4. 检查 manga-translate 命令可用
command -v manga-translate || echo "Error: manga-translate not found"
```

**自动化检查**：测试脚本 `scripts/test_translate_full.sh` 已包含所有检查。

---

### 步骤 4：执行翻译

#### 使用测试脚本（推荐）

```bash
# 设置环境变量（如果需要）
export MIMO_API_KEY="user-api-key"

# 运行脚本
bash scripts/test_translate_full.sh

# 脚本会自动：
# - 检查环境
# - 翻译所有 PDF
# - 导出完整产物
# - 生成日志
# - 显示摘要
```

#### 手动执行单个翻译

```bash
manga-translate translate data/input/manga.pdf \
  -o data/output/manga \
  --provider mimo \
  --config configs/providers.toml \
  --lang ja-zh \
  --save-json \
  2>&1 | tee data/output/manga/translation.log
```

---

### 步骤 5：验证产物

翻译完成后，**自动检查**产物是否完整：

```bash
output_dir="data/output/manga"

# 1. 检查翻译图片
if [ -d "$output_dir/translated" ]; then
    img_count=$(find "$output_dir/translated" -name "*.png" -o -name "*.jpg" | wc -l)
    echo "✅ 翻译图片：$img_count 个"
else
    echo "❌ 缺少 translated/ 目录"
fi

# 2. 检查 memory 产物
if [ -d "$output_dir/memory" ]; then
    char_count=$(find "$output_dir/memory/characters" -name "*.md" 2>/dev/null | wc -l)
    term_count=$(find "$output_dir/memory/terms" -name "*.md" 2>/dev/null | wc -l)
    echo "✅ 角色档案：$char_count 个"
    echo "✅ 术语条目：$term_count 个"
else
    echo "❌ 缺少 memory/ 目录"
fi

# 3. 检查 manifest
if [ -f "$output_dir/translated/manifest.json" ]; then
    echo "✅ manifest.json 存在"
else
    echo "❌ manifest.json 缺失"
fi

# 4. 检查 run.json
if [ -f "$output_dir/translated/run.json" ]; then
    echo "✅ run.json 存在"
else
    echo "❌ run.json 缺失"
fi
```

---

### 步骤 6：报告结果

向用户报告：

```
✅ 翻译完成！

产物位置：
  data/output/manga/
    ├── translated/           # 翻译后的图片（20 个）
    ├── memory/
    │   ├── characters/       # 角色档案（5 个）
    │   ├── terms/            # 术语库（12 个）
    │   └── state/            # JSON 状态
    ├── project_meta.toml
    └── translation.log       # 翻译日志

关键指标：
  - 页数：20
  - 角色：5
  - 术语：12
  - 耗时：3 分 45 秒
```

如果失败，报告错误并提供日志位置：

```
❌ 翻译失败

错误信息：[从日志中提取的错误]

详细日志：data/output/manga/translation.log

可能原因：
  1. API key 未设置或无效
  2. 网络连接问题
  3. PDF 文件损坏

建议：
  - 检查 MIMO_API_KEY 环境变量
  - 查看日志文件获取详细错误
```

---

## 常见变体处理

### 变体 1：用户要求使用特定模型

**用户**："用 gpt-4o 翻译"

**识别**：需要切换 provider

**执行**：
```bash
# 方法 1：修改配置文件 configs/providers.toml
[stages.translation]
primary = "openai"

[providers.openai]
vision_model = "gpt-4o"
text_model = "gpt-4o"

# 方法 2：命令行指定
manga-translate translate ... --provider openai --config configs/providers.toml
```

---

### 变体 2：用户要求热启动

**用户**："用前 10 话的翻译学习，翻译第 11 话"

**识别**：需要 `--learn-from` 参数

**执行**：
```bash
manga-translate translate data/input/chapter_11.pdf \
  -o data/output/chapter_11 \
  --learn-from data/output/chapters_01_10 \
  --provider mimo \
  --config configs/providers.toml \
  --save-json
```

---

### 变体 3：用户要求双语对照

**用户**："生成双语 PDF"

**识别**：需要 `--bilingual` 参数

**执行**：
```bash
manga-translate translate data/input/manga.pdf \
  -o data/output/manga \
  --bilingual \
  --provider mimo \
  --config configs/providers.toml
```

输出：`data/output/manga/bilingual.pdf`（左页原文，右页译文）

---

### 变体 4：用户只要求提取角色档案

**用户**："从这些已翻译的文件中提取角色档案"

**识别**：`--learn-only` 模式

**执行**：
```bash
manga-translate translate data/translated/ \
  --learn-only \
  --learn-from data/translated/ \
  -o data/output/profiles
```

---

## 故障排查清单

当翻译失败时，按以下顺序检查：

1. **输入文件检查**
   ```bash
   file data/input/manga.pdf  # 是否是有效 PDF
   ls -lh data/input/manga.pdf  # 文件大小是否合理
   ```

2. **环境变量检查**
   ```bash
   echo $MIMO_API_KEY  # 是否已设置
   ```

3. **配置文件检查**
   ```bash
   cat configs/providers.toml  # 配置是否正确
   ```

4. **网络连接检查**
   ```bash
   curl -I https://token-plan-cn.xiaomimomo.com/v1  # API 是否可访问
   ```

5. **权限检查**
   ```bash
   ls -la data/output/  # 输出目录是否可写
   ```

6. **日志检查**
   ```bash
   tail -n 50 data/output/manga/translation.log  # 查看错误信息
   ```

---

## 快速参考

### 最常用命令（复制粘贴）

```bash
# 一键批量翻译（推荐）
bash scripts/test_translate_full.sh

# 单文件翻译（完整产物）
manga-translate translate INPUT.pdf -o OUTPUT_DIR --provider mimo --config configs/providers.toml --save-json

# 检查产物
ls -lh OUTPUT_DIR/translated/
ls OUTPUT_DIR/memory/characters/
cat OUTPUT_DIR/translated/run.json
```

### 文档索引

- **命令速查表**：`docs/COMMAND_CHEATSHEET.md`
- **详细测试指南**：`docs/TESTING_GUIDE.md`
- **代码审查**：`docs/CODE_REVIEW_CHECKLIST.md`
- **项目说明**：`README.md`
- **架构说明**：`CLAUDE.md`

---

## Agent 执行模板

```markdown
## 理解需求
用户要求：[总结用户需求]

确认信息：
- 输入：[路径]
- 输出：[路径]
- Provider：[名称]
- 语言：[语言对]
- 完整产物：是/否

## 执行计划
方案：[方案 A/B]
命令：[具体命令]

## 前置检查
- [ ] 输入文件存在
- [ ] 配置文件存在
- [ ] API key 已设置（如需要）
- [ ] manga-translate 可用

## 执行
[运行命令的结果]

## 验证
- [ ] 翻译图片（XX 个）
- [ ] 角色档案（XX 个）
- [ ] 术语库（XX 个）
- [ ] manifest.json
- [ ] run.json

## 报告
[向用户报告结果]
```

---

**记住**：
1. 优先使用 `scripts/test_translate_full.sh`（已包含所有检查和日志）
2. 总是添加 `--save-json` 以导出完整产物
3. 执行前检查环境，执行后验证产物
4. 失败时提供详细日志和排查建议
