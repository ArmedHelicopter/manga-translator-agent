# Manga Translate Agent - 命令速查表

## 🚀 最常用命令

### 翻译单个文件（完整产物）
```bash
manga-translate translate INPUT.pdf -o OUTPUT_DIR --provider mimo --config configs/providers.toml --save-json
```

**产物位置**：
- 翻译图片：`OUTPUT_DIR/translated/`
- 角色档案：`OUTPUT_DIR/memory/characters/`
- 术语库：`OUTPUT_DIR/memory/terms/`
- JSON 状态：`OUTPUT_DIR/memory/state/`

---

### 一键测试脚本（批量翻译）
```bash
# 翻译 data/input/*.pdf → data/output/
bash scripts/test_translate_full.sh
```

---

## 📋 翻译命令模板

### 基础翻译（日→中）
```bash
manga-translate translate <输入.pdf> \
  -o <输出目录> \
  --provider mimo \
  --config configs/providers.toml \
  --lang ja-zh \
  --save-json
```

### 热启动翻译（利用已有翻译）
```bash
manga-translate translate <新章节.pdf> \
  -o <输出目录> \
  --learn-from <已翻译章节目录> \
  --provider mimo \
  --config configs/providers.toml \
  --save-json
```

### 双语对照输出
```bash
manga-translate translate <输入.pdf> \
  -o <输出目录> \
  --bilingual \
  --provider mimo \
  --config configs/providers.toml
```

### 只学习不翻译（提取角色档案）
```bash
manga-translate translate <已翻译目录> \
  --learn-only \
  --learn-from <已翻译目录> \
  -o <输出目录>
```

---

## 🔍 查询命令

### 查看角色档案
```bash
manga-translate profile list <项目目录>
manga-translate profile show <项目目录> <角色ID>
```

### 查看术语库
```bash
manga-translate term list <项目目录>
manga-translate term show <项目目录> <术语>
```

### 同步 Memory
```bash
# 从 JSON state 重新生成 Markdown wiki
manga-translate memory sync <项目目录>
```

---

## 📦 批量处理

### 创建批量配置
```json
{
  "chapters": [
    {"input_path": "ch1.pdf", "output_path": "out/ch1", "chapter_id": "ch1"},
    {"input_path": "ch2.pdf", "output_path": "out/ch2", "chapter_id": "ch2"}
  ]
}
```

### 运行批量翻译
```bash
manga-translate batch process batch_config.json \
  --project-dir <项目目录> \
  --max-workers 2 \
  --provider mimo \
  --config configs/providers.toml
```

---

## ⚙️ 配置文件示例

### configs/providers.toml
```toml
[stages.vision]
primary = "mimo"

[stages.translation]
primary = "mimo"

[stages.qa]
primary = "mimo"

[providers.mimo]
provider_type = "openai"
api_key_env = "MIMO_API_KEY"
base_url = "https://token-plan-cn.xiaomimomo.com/v1"
vision_model = "mimo-v2.5-pro"
text_model = "mimo-v2.5-pro"

[providers.openai]
provider_type = "openai"
api_key_env = "OPENAI_API_KEY"
vision_model = "gpt-4o"
text_model = "gpt-4o-mini"
```

### 环境变量
```bash
export MIMO_API_KEY="your-key-here"
export OPENAI_API_KEY="your-key-here"
```

---

## 🧪 测试和调试

### 自动化审查
```bash
python scripts/pre_review_check.py         # 全部检查
python scripts/pre_review_check.py --check layers
python scripts/pre_review_check.py --check security
```

### 运行测试
```bash
# 快速测试（无 torch）
pytest tests/ -q --tb=short \
  --ignore=tests/artifacts/test_run_summary.py \
  --ignore=tests/pipeline/test_batch.py \
  --ignore=tests/pipeline/test_character_memory_demo.py \
  --ignore=tests/pipeline/test_graph_integration.py \
  --ignore=tests/pipeline/test_incremental.py

# 完整测试
pytest tests/ -v
```

### 启用调试日志
```bash
export MGA_LOG_LEVEL=DEBUG
manga-translate translate ...
```

---

## 📂 产物结构

翻译完成后的目录结构：
```
<输出目录>/
├── translated/              # 翻译后的图片
│   ├── page_0001.png
│   ├── manifest.json
│   └── run.json
├── memory/                  # Memory + Wiki
│   ├── state/               # JSON 状态（机器可读）
│   │   ├── characters/
│   │   ├── terms/
│   │   └── index.json
│   ├── characters/          # Markdown wiki（人类可读）
│   ├── terms/
│   └── scenes/
└── project_meta.toml
```

---

## 🆘 故障排查

### 翻译失败
```bash
# 检查日志
cat <输出目录>/translation.log

# 常见原因
1. API key 未设置：export MIMO_API_KEY="..."
2. 网络问题：检查 base_url 是否可访问
3. PDF 损坏：使用 pdfinfo 检查文件
```

### 内存不足
```bash
# 减少并行度
manga-translate batch ... --max-workers 1

# 或分批处理
```

### Provider 不可用
```bash
# 切换到备用 provider
manga-translate translate ... --provider openai --config configs/providers.toml
```

---

## 📚 文档索引

| 文档 | 说明 |
|------|------|
| [TESTING_GUIDE.md](./TESTING_GUIDE.md) | 完整测试指南（详细版） |
| [CODE_REVIEW_CHECKLIST.md](./CODE_REVIEW_CHECKLIST.md) | 代码审查检查清单 |
| [SPEC.md](./SPEC.md) | 功能规格 |
| [PRD.md](./PRD.md) | 产品需求 |
| [CLAUDE.md](../CLAUDE.md) | 架构说明 |
| [README.md](../README.md) | 项目说明 |

---

## 💡 提示

### 快速记忆
- `translate` = 翻译管道
- `--save-json` = 导出所有产物
- `--learn-from` = 热启动
- `--bilingual` = 双语对照
- `profile/term` = 查询命令
- `memory sync` = 同步 wiki

### Provider 选择
- `mimo` = mimo-v2.5-pro（在线）
- `openai` = GPT-4o（在线）
- `gemini` = Gemini 2.5 Pro（在线）
- `ollama` = 本地模型

### 输出格式
- `--format pdf` = PDF 输出
- `--format epub` = EPUB 输出
- `--format cbz` = CBZ 输出
- `--bilingual` = 双语 PDF

---

**快速开始**：
```bash
# 1. 准备输入
mkdir -p data/input && cp manga.pdf data/input/

# 2. 设置 API key
export MIMO_API_KEY="your-key"

# 3. 一键翻译
bash scripts/test_translate_full.sh
```
