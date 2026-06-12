# 端到端翻译测试指南

本文档说明如何进行完整的漫画翻译测试，包括翻译、RAG、wiki、角色档案等所有产物的导出。

## 快速开始（一键测试）

```bash
# 1. 准备输入文件
mkdir -p data/input
cp your_manga.pdf data/input/

# 2. 设置 API key（如果需要）
export MIMO_API_KEY="your-api-key-here"

# 3. 运行测试脚本
bash scripts/test_translate_full.sh
```

脚本会自动：
- ✅ 检查环境和依赖
- ✅ 翻译所有 `data/input/*.pdf`
- ✅ 导出翻译图片到 `data/output/<文件名>/translated/`
- ✅ 导出 wiki 和 RAG 产物到 `data/output/<文件名>/memory/`
- ✅ 生成完整日志

---

## 手动测试（了解每一步）

### 1. 准备工作

#### 1.1 创建目录结构

```bash
mkdir -p data/input
mkdir -p data/output
```

#### 1.2 准备输入文件

```bash
# 复制 PDF 到输入目录
cp ~/Downloads/manga_volume1.pdf data/input/
```

#### 1.3 检查配置文件

确保 `configs/providers.toml` 存在且配置正确：

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
```

#### 1.4 设置环境变量

```bash
export MIMO_API_KEY="your-api-key-here"
export MIMO_BASE_URL="https://token-plan-cn.xiaomimomo.com/v1"  # 可选
```

---

### 2. 翻译单个文件

```bash
# 基本翻译
manga-translate translate data/input/manga_volume1.pdf \
  -o data/output/manga_volume1 \
  --provider mimo \
  --config configs/providers.toml \
  --lang ja-zh \
  --save-json

# 说明：
# - data/input/manga_volume1.pdf：输入文件
# - data/output/manga_volume1：输出目录（作为项目目录）
# - --provider mimo：使用 mimo provider
# - --config：指定配置文件
# - --lang ja-zh：日语到中文
# - --save-json：保存完整的 JSON 产物
```

---

### 3. 初始化 Memory 结构（可选，翻译时会自动创建）

```bash
manga-translate memory init data/output/manga_volume1
```

这会创建：
```
data/output/manga_volume1/
├── memory/
│   ├── state/              # JSON canonical source
│   │   ├── characters/
│   │   ├── terms/
│   │   ├── scenes/
│   │   ├── decisions/
│   │   └── index.json
│   ├── characters/         # Markdown wiki projection
│   ├── terms/
│   ├── scenes/
│   └── indexes/
└── project_meta.toml
```

---

### 4. 查看产物

#### 4.1 翻译图片

```bash
ls -lh data/output/manga_volume1/translated/
# 输出：page_0001.png, page_0002.png, ...
```

#### 4.2 角色档案（Markdown）

```bash
ls data/output/manga_volume1/memory/characters/
# 输出：character_name1.md, character_name2.md, ...

cat data/output/manga_volume1/memory/characters/amamiya_akari.md
```

#### 4.3 术语库（Markdown）

```bash
ls data/output/manga_volume1/memory/terms/
# 输出：term_name1.md, term_name2.md, ...
```

#### 4.4 JSON 状态（Canonical）

```bash
cat data/output/manga_volume1/memory/state/index.json
cat data/output/manga_volume1/memory/state/characters/amamiya_akari.json
```

#### 4.5 翻译报告

```bash
cat data/output/manga_volume1/translated/run.json
cat data/output/manga_volume1/translated/manifest.json
```

---

### 5. 热启动翻译（利用已有翻译学习）

如果你已经翻译了第 1-10 话，现在翻译第 11 话：

```bash
manga-translate translate data/input/chapter_11.pdf \
  -o data/output/chapter_11 \
  --learn-from data/output/chapter_01_to_10 \
  --provider mimo \
  --config configs/providers.toml \
  --lang ja-zh \
  --save-json
```

`--learn-from` 会：
- 从已有翻译中提取角色档案
- 提取术语库
- 提取翻译风格
- 应用到新翻译中

---

### 6. 批量翻译多个文件

创建批量配置文件 `batch_config.json`：

```json
{
  "chapters": [
    {
      "input_path": "data/input/volume1.pdf",
      "output_path": "data/output/volume1",
      "chapter_id": "volume1"
    },
    {
      "input_path": "data/input/volume2.pdf",
      "output_path": "data/output/volume2",
      "chapter_id": "volume2"
    }
  ]
}
```

运行批量翻译：

```bash
manga-translate batch process batch_config.json \
  --project-dir data/output/project \
  --max-workers 2 \
  --provider mimo \
  --config configs/providers.toml
```

---

## 产物结构说明

翻译完成后，输出目录结构如下：

```
data/output/
└── <文件名>/                    # 项目目录（每个 PDF 一个）
    ├── translated/              # 翻译后的图片
    │   ├── page_0001.png
    │   ├── page_0002.png
    │   ├── ...
    │   ├── manifest.json        # 页面元数据
    │   └── run.json             # 运行摘要
    │
    ├── memory/                  # Memory + Wiki 产物
    │   ├── state/               # JSON canonical source（机器可读）
    │   │   ├── characters/      # 角色状态 JSON
    │   │   │   ├── character1.json
    │   │   │   └── character2.json
    │   │   ├── terms/           # 术语状态 JSON
    │   │   ├── scenes/          # 场景状态 JSON
    │   │   ├── decisions/       # 决策状态 JSON
    │   │   └── index.json       # 索引
    │   │
    │   ├── characters/          # 角色 wiki（人类可读）
    │   │   ├── character1.md
    │   │   └── character2.md
    │   │
    │   ├── terms/               # 术语 wiki
    │   │   ├── term1.md
    │   │   └── term2.md
    │   │
    │   ├── scenes/              # 场景 wiki
    │   ├── decisions/           # 决策 wiki
    │   └── indexes/             # 索引页
    │
    ├── project_meta.toml        # 项目元数据
    └── translation.log          # 翻译日志（如果使用测试脚本）
```

---

## 常见问题

### Q1: 如何只导出 wiki，不翻译？

```bash
# 使用 --learn-only 模式
manga-translate translate existing_translated/ \
  --learn-only \
  --learn-from existing_translated/ \
  -o data/output/wiki_only
```

### Q2: 如何查看角色档案列表？

```bash
manga-translate profile list data/output/manga_volume1
```

### Q3: 如何查看术语库？

```bash
manga-translate term list data/output/manga_volume1
```

### Q4: 如何同步 memory 状态？

```bash
# 从 JSON state 重新生成 Markdown wiki
manga-translate memory sync data/output/manga_volume1
```

### Q5: 翻译失败怎么办？

检查日志：
```bash
# 如果使用测试脚本
cat data/output/<文件名>/translation.log

# 或查看终端输出
manga-translate translate ... 2>&1 | tee translation.log
```

常见原因：
- API key 未设置或无效
- 网络连接问题
- PDF 文件损坏
- 内存不足

### Q6: 如何使用其他模型？

修改 `configs/providers.toml`：

```toml
[providers.openai]
provider_type = "openai"
api_key_env = "OPENAI_API_KEY"
vision_model = "gpt-4o"
text_model = "gpt-4o-mini"

[stages.vision]
primary = "openai"

[stages.translation]
primary = "openai"
```

然后：
```bash
manga-translate translate ... --provider openai --config configs/providers.toml
```

### Q7: 如何生成双语对照 PDF？

```bash
manga-translate translate data/input/manga.pdf \
  -o data/output/manga \
  --bilingual \
  --provider mimo \
  --config configs/providers.toml
```

输出：`data/output/manga/bilingual.pdf`（左页原文，右页译文）

---

## 性能优化

### 使用批量处理提高并行度

```bash
manga-translate batch process batch_config.json \
  --max-workers 4 \
  --project-dir data/output/project
```

### 复用 runtime payload（跳过 Pass 1）

如果已经运行过 external runtime 导出：

```bash
manga-translate translate data/input/manga.pdf \
  -o data/output/manga \
  --artifact-payload-dir path/to/existing/payload \
  --provider mimo
```

---

## 调试技巧

### 启用详细日志

```bash
export MGA_LOG_LEVEL=DEBUG
manga-translate translate ...
```

### 保存所有 JSON 产物

```bash
manga-translate translate ... --save-json
```

这会保存：
- `translations/<page_id>.json` — 每页的翻译详情
- `qa_report.json` — QA 校对报告
- `translation_report.json` — 完整翻译报告

### 干运行（不实际翻译）

```bash
manga-translate translate ... --dry-run
```

---

## 脚本参数说明

测试脚本 `scripts/test_translate_full.sh` 接受以下环境变量：

```bash
# 输入目录（默认：./data/input）
INPUT_DIR="./my/input" bash scripts/test_translate_full.sh

# 输出目录（默认：./data/output）
OUTPUT_BASE="./my/output" bash scripts/test_translate_full.sh

# 配置文件（默认：./configs/providers.toml）
CONFIG="./my/config.toml" bash scripts/test_translate_full.sh

# Provider（默认：mimo）
PROVIDER="openai" bash scripts/test_translate_full.sh

# 语言对（默认：ja-zh）
LANG="en-zh" bash scripts/test_translate_full.sh
```

---

## 相关文档

- [SPEC.md](../docs/SPEC.md) — 功能规格
- [PRD.md](../docs/PRD.md) — 产品需求
- [README.md](../README.md) — 项目说明
- [CLAUDE.md](../CLAUDE.md) — 架构说明

---

**下一步**：
- 运行 `bash scripts/test_translate_full.sh` 进行完整测试
- 查看 `data/output/` 目录中的产物
- 根据需要调整配置文件
