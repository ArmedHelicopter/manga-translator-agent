# 📘 文档与工具总结

## 问题：LLM 跑全量产出很费劲

**用户场景**：
> "用 ./data/input/*.pdf 跑一次全量日语翻译到中文测试，输出到 ./data/output/ 对应文件夹，模型用在线供应商的 mimo-v2.5-pro。要求 wiki 和 rag 等产物也要导出到 ./data/output 对应文件夹"

**问题**：
- LLM 不知道具体命令是什么
- 需要一个一个查看脚本和文档
- 缺少决策树和执行模板
- 没有自动化检查和验证

---

## 解决方案：3 层文档 + 2 个脚本

### 📚 文档层（从快到详细）

#### 1. [COMMAND_CHEATSHEET.md](./COMMAND_CHEATSHEET.md) — 命令速查表（5KB）
**用途**：最快速的命令查找

**内容**：
- 最常用的 5 个命令（复制粘贴即用）
- 翻译命令模板（基础/热启动/双语/学习）
- 查询命令（profile/term/memory）
- 批量处理模板
- 配置文件示例
- 产物结构图
- 故障排查

**适用**：
- ✅ 用户快速查命令
- ✅ AI Agent 快速复制命令
- ✅ 紧急情况速查

---

#### 2. [AGENT_GUIDE.md](./AGENT_GUIDE.md) — Agent 使用指南（9.5KB）
**用途**：专门为 AI Agent 编写的执行手册

**内容**：
- 场景识别（如何判断用户要什么）
- 快速决策树（单文件 vs 批量 vs 学习）
- 标准执行流程（6 个步骤）
- 前置检查清单
- 验证产物清单
- 常见变体处理（热启动/双语/学习）
- 故障排查清单
- Agent 执行模板（Markdown 模板）

**适用**：
- ✅ AI Agent（Kiro、Claude Code）执行翻译测试
- ✅ 自动化脚本开发者
- ✅ 需要理解决策逻辑的用户

**关键亮点**：
```
场景识别 → 决策树 → 执行计划 → 前置检查 → 执行 → 验证 → 报告
```

---

#### 3. [TESTING_GUIDE.md](./TESTING_GUIDE.md) — 完整测试指南（9.4KB）
**用途**：详细的测试流程和说明

**内容**：
- 快速开始（一键测试）
- 手动测试（6 个步骤，每步详细说明）
- 产物结构完整说明
- 常见问题 Q&A（7 个问题）
- 性能优化技巧
- 调试技巧
- 脚本参数说明

**适用**：
- ✅ 需要深入理解的用户
- ✅ 排查问题时的参考
- ✅ 学习项目功能

---

### 🛠️ 脚本层（自动化执行）

#### 1. [test_translate_full.sh](../scripts/test_translate_full.sh) — 一键翻译脚本（5.7KB）
**功能**：
- ✅ 自动检查环境（输入目录、配置文件、API key）
- ✅ 批量翻译所有 `data/input/*.pdf`
- ✅ 自动初始化 memory 结构
- ✅ 导出完整产物（translated/ + memory/ + logs）
- ✅ 统计成功/失败数量
- ✅ 彩色日志输出
- ✅ 生成详细摘要

**使用**：
```bash
# 默认配置
bash scripts/test_translate_full.sh

# 自定义配置
INPUT_DIR="./my/input" OUTPUT_BASE="./my/output" bash scripts/test_translate_full.sh
```

**输出**：
```
data/output/
├── <文件名1>/
│   ├── translated/          # 翻译图片
│   ├── memory/              # wiki + RAG
│   └── translation.log      # 日志
└── <文件名2>/
    └── ...
```

---

#### 2. [pre_review_check.py](../scripts/pre_review_check.py) — 自动化审查脚本（12KB）
**功能**：
- ✅ 层边界检查（跨层导入）
- ✅ 异常层级检查（裸异常）
- ✅ 安全扫描（硬编码密钥、注入风险）
- ✅ JSON 解析一致性
- ✅ 类型注解检查
- ✅ 测试可执行性
- ✅ 依赖版本检查

**使用**：
```bash
# 全部检查
python scripts/pre_review_check.py

# 特定检查
python scripts/pre_review_check.py --check layers
python scripts/pre_review_check.py --check security
```

---

### 📖 代码审查文档

#### [CODE_REVIEW_CHECKLIST.md](./CODE_REVIEW_CHECKLIST.md) — 审查清单（6KB）
- 9 大类检查项（架构/质量/安全/测试/依赖/文档/性能/回归）
- 自动化脚本使用说明
- 提交前检查清单

#### [code-reviews/2026-06-06-full-review.md](./code-reviews/2026-06-06-full-review.md) — 完整审查报告（8KB）
- 发现的 32 个问题详情
- 应用的 6 个修复
- SPEC/PRD 合规性评估
- 测试结果（529/530 通过）
- 遗留问题和后续行动

#### [code-reviews/SUMMARY.md](./code-reviews/SUMMARY.md) — 审查总结（5KB）
- 执行流程图
- 修复成果表
- 测试结果
- 自动化检查结果
- 遗留问题

---

## 使用场景映射

| 场景 | 推荐文档/脚本 | 用时 |
|------|--------------|------|
| **用户：快速查命令** | [COMMAND_CHEATSHEET.md](./COMMAND_CHEATSHEET.md) | 30 秒 |
| **用户：运行翻译测试** | `bash scripts/test_translate_full.sh` | 1 分钟设置 + N 分钟翻译 |
| **用户：理解完整流程** | [TESTING_GUIDE.md](./TESTING_GUIDE.md) | 5-10 分钟 |
| **AI Agent：执行测试** | [AGENT_GUIDE.md](./AGENT_GUIDE.md) | 2 分钟理解 + 执行 |
| **开发者：代码审查** | `python scripts/pre_review_check.py` | 30 秒 |
| **开发者：手动审查** | [CODE_REVIEW_CHECKLIST.md](./CODE_REVIEW_CHECKLIST.md) | 15-30 分钟 |
| **项目维护者：了解质量** | [code-reviews/SUMMARY.md](./code-reviews/SUMMARY.md) | 3 分钟 |

---

## AI Agent 快速执行模板

当用户说："用 ./data/input/*.pdf 跑一次全量日语翻译到中文测试"

### 步骤 1：快速决策（10 秒）

```markdown
理解需求：批量翻译 PDF，导出完整产物
方案：使用一键测试脚本
```

### 步骤 2：执行（1 分钟）

```bash
# 1. 检查输入
ls data/input/*.pdf

# 2. 设置 API key（如需要）
export MIMO_API_KEY="..."

# 3. 运行脚本
bash scripts/test_translate_full.sh
```

### 步骤 3：报告（1 分钟）

```markdown
✅ 翻译完成

产物：
- data/output/file1/translated/ (20 张图片)
- data/output/file1/memory/ (5 个角色，12 个术语)
- data/output/file2/translated/ (18 张图片)
- data/output/file2/memory/ (4 个角色，9 个术语)

总计：2 个文件，38 张图片，9 个角色，21 个术语

详细日志：
- data/output/file1/translation.log
- data/output/file2/translation.log
```

---

## 文档索引

### 用户文档
- [README.md](../README.md) — 项目说明
- [COMMAND_CHEATSHEET.md](./COMMAND_CHEATSHEET.md) — 命令速查表 ⭐
- [TESTING_GUIDE.md](./TESTING_GUIDE.md) — 完整测试指南
- [SPEC.md](./SPEC.md) — 功能规格
- [PRD.md](./PRD.md) — 产品需求
- [ROADMAP.md](./ROADMAP.md) — 路线图

### AI Agent 文档
- [AGENT_GUIDE.md](./AGENT_GUIDE.md) — Agent 执行手册 ⭐

### 开发者文档
- [CLAUDE.md](../CLAUDE.md) — 架构说明
- [CODE_REVIEW_CHECKLIST.md](./CODE_REVIEW_CHECKLIST.md) — 审查清单
- [code-reviews/](./code-reviews/) — 审查报告

### 脚本
- `scripts/test_translate_full.sh` — 一键翻译脚本 ⭐
- `scripts/pre_review_check.py` — 自动化审查 ⭐

---

## 关键改进

### Before（问题）
```
用户："用 ./data/input/*.pdf 跑一次翻译"
AI："需要查看文档..."
[查看 README.md]
AI："还需要查看 CLI 帮助..."
[运行 manga-translate --help]
AI："需要看配置文件..."
[查看 configs/]
AI："不确定怎么导出 wiki..."
[继续查找...]
```

**耗时**：5-10 分钟，多次查找

---

### After（解决）
```
用户："用 ./data/input/*.pdf 跑一次翻译"
AI：[读取 AGENT_GUIDE.md]
AI："识别为批量翻译场景，使用方案 B"
AI："运行检查和脚本..."
[执行 bash scripts/test_translate_full.sh]
AI："✅ 完成，产物位置：..."
```

**耗时**：1-2 分钟，一次执行

**效率提升**：5-10 倍

---

## 总结

| 文档/脚本 | 用途 | 目标用户 | 大小 |
|----------|------|---------|------|
| COMMAND_CHEATSHEET | 快速查命令 | 用户 + AI | 5KB |
| AGENT_GUIDE | 执行决策树 | AI Agent | 9.5KB |
| TESTING_GUIDE | 完整流程说明 | 用户 | 9.4KB |
| test_translate_full.sh | 一键翻译 | 用户 + AI | 5.7KB |
| pre_review_check.py | 自动化审查 | 开发者 | 12KB |
| CODE_REVIEW_CHECKLIST | 手动审查清单 | 开发者 | 6KB |
| 2026-06-06-full-review.md | 审查报告示例 | 团队 | 8KB |

**总计**：7 个文档 + 2 个脚本，~55KB，覆盖所有使用场景。

---

**下次 LLM 执行测试时**：
1. 读 `docs/AGENT_GUIDE.md`（决策树）
2. 运行 `scripts/test_translate_full.sh`（一键执行）
3. 验证产物（自动检查清单）
4. 报告结果（模板）

**10 倍效率提升！** 🚀
