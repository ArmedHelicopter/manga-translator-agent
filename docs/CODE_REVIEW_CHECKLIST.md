# 代码审查检查清单

> 本文档提供了针对 Manga Translate Agent (mga) 项目的代码审查指南和自动化检查脚本。

## 快速检查脚本

```bash
# 运行所有自动检查
python scripts/pre_review_check.py

# 或手动运行各项检查
python scripts/pre_review_check.py --check imports
python scripts/pre_review_check.py --check layers
python scripts/pre_review_check.py --check security
python scripts/pre_review_check.py --check tests
```

---

## 1. 架构合规性检查（自动化）

### 1.1 层边界检查

**规则**：低层不得导入高层模块

```
Layer 0 (Models)     → 仅依赖 Pydantic、typing
Layer 1 (Infra)      → 可依赖 Layer 0
Layer 2 (Intelligence) → 可依赖 Layer 0-1
Layer 3 (Pipeline)   → 可依赖 Layer 0-2
Layer 4 (CLI)        → 可依赖 Layer 0-3
Layer 5 (Runtime)    → 独立模块，不依赖其他层
```

**检查命令**：
```bash
# 检查所有跨层导入
grep -rn "from manga_translator" mga/pipeline/ mga/providers/ mga/memory/ mga/cultural/
grep -rn "from mga.pipeline" mga/models/ mga/config/ mga/providers/
grep -rn "from mga.memory" mga/models/ mga/config/
```

**预期结果**：无输出（无违规导入）

---

### 1.2 异常层级检查

**规则**：所有领域异常必须继承自 `MangaTranslateError`

**检查命令**：
```bash
# 查找裸 Exception 使用
grep -rn "raise Exception" mga/
grep -rn "except Exception" mga/ | wc -l  # 应 ≤ 0 或有明确理由
```

**预期结果**：
- 无 `raise Exception("...")`
- `except Exception` 应仅用于记录后重新抛出，或捕获后转换为领域异常

---

## 2. 代码质量检查（半自动）

### 2.1 类型安全

**检查点**：
- [ ] 所有公共函数有类型注解
- [ ] 使用 `from __future__ import annotations` 避免前向引用问题
- [ ] 避免使用 `Any` 类型（除非确有必要）

**检查命令**：
```bash
# 查找缺少类型注解的函数
rg "^def \w+\([^)]*\):" mga/ --type py | grep -v "__init__\|__repr__\|__str__"

# 查找过多使用 Any 的地方
grep -rn ": Any" mga/ | wc -l
```

---

### 2.2 资源管理

**检查点**：
- [ ] 文件操作使用 `with` 语句或 `Path.read_text()`/`write_text()`
- [ ] 线程安全：共享状态使用锁保护
- [ ] 异步函数正确使用 `async with`

**检查命令**：
```bash
# 查找裸 open() 调用（应使用 with 或 Path）
grep -rn "open(" mga/ | grep -v "with open"

# 查找共享状态但无锁的类
grep -rn "ThreadPoolExecutor\|threading.Thread" mga/
```

---

### 2.3 JSON 解析统一性

**规则**：所有 LLM 响应的 JSON 解析应使用 `mga.util.parse_json_from_llm_response`

**检查命令**：
```bash
# 查找本地 JSON 解析实现
grep -rn "json.loads\|json.dumps" mga/providers/ mga/pipeline/ | grep -v "parse_json_from_llm_response"
```

**预期结果**：
- `json.loads` 仅用于读取配置文件和产物存储
- LLM 响应解析必须通过统一工具

---

## 3. 安全检查（自动化）

### 3.1 敏感信息泄露

**检查命令**：
```bash
# 查找硬编码密钥
grep -rn "api_key\s*=\s*['\"]" mga/ configs/
grep -rn "password\s*=\s*['\"]" mga/ configs/

# 查找绝对路径泄露（Web API）
grep -rn "path=str(" mga/web/
```

**预期结果**：无硬编码凭据，无绝对路径在 API 响应中

---

### 3.2 注入风险

**检查命令**：
```bash
# 查找命令注入风险
grep -rn "subprocess.call\|os.system" mga/ | grep "shell=True"

# 查找 SQL 注入风险（无 SQL 数据库，应为空）
grep -rn "execute(" mga/ | grep -v "stage.execute"

# 查找路径遍历风险
grep -rn "os.path.join\|Path(" mga/web/ mga/cli/
```

**预期结果**：
- 无 `shell=True` 的子进程调用
- 无原始 SQL 查询
- 路径操作有边界检查（如 `_ensure_under_root`）

---

## 4. 测试覆盖率检查

### 4.1 关键路径测试

**必须有测试的模块**：
- [ ] `mga/providers/` — 每个 provider 的基本功能
- [ ] `mga/pipeline/` — 每个 stage 的执行
- [ ] `mga/memory/` — state 读写、wiki 投影
- [ ] `mga/qa/` — 每个校对器的基本逻辑
- [ ] `mga/util/json.py` — 统一 JSON 解析器的边界情况

**检查命令**：
```bash
# 查看测试覆盖率
pytest tests/ --cov=mga --cov-report=term-missing

# 查找缺少测试的模块
ls mga/*/*.py | while read f; do 
  base=$(basename $f .py)
  if ! ls tests/*/test_$base.py 2>/dev/null; then
    echo "Missing test: $f"
  fi
done
```

---

### 4.2 测试执行

**检查命令**：
```bash
# 快速测试（排除需要 torch 的测试）
pytest tests/ -q --tb=short \
  --ignore=tests/artifacts/test_run_summary.py \
  --ignore=tests/pipeline/test_batch.py \
  --ignore=tests/pipeline/test_character_memory_demo.py \
  --ignore=tests/pipeline/test_graph_integration.py \
  --ignore=tests/pipeline/test_incremental.py \
  --ignore=tests/pipeline/test_novel_pipeline.py \
  --ignore=tests/pipeline/test_ocr_vision_split.py \
  --ignore=tests/pipeline/test_page_sequential_memory_integration.py \
  --ignore=tests/pipeline/test_profile_injection.py \
  --ignore=tests/pipeline/test_speaker_attribution_stage.py

# 完整测试（需要 torch）
pytest tests/ -v
```

**预期结果**：≥ 95% 通过率

---

## 5. 依赖管理检查

### 5.1 版本一致性

**检查命令**：
```bash
# 检查 pyproject.toml vs 实际环境
pip list --format=freeze | grep -E "pydantic|pytest|openai|httpx|numpy"
cat pyproject.toml | grep -A 20 dependencies | grep -E "pydantic|pytest|openai|httpx|numpy"
```

**预期结果**：
- 实际安装版本符合 `pyproject.toml` 的约束
- 固定版本的依赖（如 `pydantic==2.5.0`）不应有版本漂移

---

### 5.2 可选依赖处理

**规则**：可选依赖缺失时应降级优雅，不应崩溃

**检查命令**：
```bash
# 验证可选依赖的导入保护
grep -rn "import anthropic" mga/providers/anthropic_provider.py
grep -rn "import torch" mga/
```

**预期结果**：
- `torch` 导入在 `manga_translator` 包内，`mga` 不直接导入
- 可选 provider 导入失败时应在注册时标记为不可用

---

## 6. 文档检查

### 6.1 必需文档

- [ ] `README.md` — 安装指南、快速开始
- [ ] `CLAUDE.md` — 架构说明、层边界、编码规范
- [ ] `docs/SPEC.md` — 功能规格、设计决策
- [ ] `docs/PRD.md` — 产品需求、路线图
- [ ] `pyproject.toml` — 依赖声明、项目元数据

---

### 6.2 代码文档

**检查点**：
- [ ] 所有公共类有 docstring
- [ ] 复杂函数有参数和返回值说明
- [ ] 重要设计决策有注释说明

**检查命令**：
```bash
# 查找缺少 docstring 的公共类
rg "^class [A-Z]\w+.*:" mga/ --type py -A 1 | grep -v '"""' | grep "class"
```

---

## 7. 性能检查（手动）

### 7.1 已知热点

**检查点**：
- [ ] `OutputStage._write_translations` — 避免 O(N²) 遍历
- [ ] `TerminologyDB.load` — 确认有缓存机制
- [ ] `StateManager.load` — 避免每次管道运行都重新加载 `index.json`
- [ ] `BatchProcessor._save_progress` — 确认有锁保护

**检查方式**：代码审查时关注这些方法

---

## 8. 回归检查清单

在修改代码后，检查以下场景：

- [ ] 单页翻译：`manga-translate input.jpg -o output/`
- [ ] 批量翻译：`manga-translate input_dir/ -o output_dir/`
- [ ] 热启动：`manga-translate new/ --learn-from existing/ -o output/`
- [ ] 格式转换：`manga-translate input.pdf -o output.epub`
- [ ] 双语输出：`manga-translate input/ --bilingual -o bilingual.pdf`
- [ ] Web UI：`manga-translate web` → 访问 http://localhost:8000
- [ ] MCP Server：`manga-translate mcp` → 验证 stdio 响应

---

## 9. 提交前检查清单

- [ ] 所有测试通过（至少 95%）
- [ ] 无新增跨层导入
- [ ] 无硬编码密钥或绝对路径泄露
- [ ] 新增公共 API 有类型注解和 docstring
- [ ] 如有重大更改，`docs/SPEC.md` 或 `CLAUDE.md` 已更新

---

## 附录：自动化脚本位置

```
scripts/
├── pre_review_check.py   # 主检查脚本
├── layer_check.py        # 层边界检查
├── security_scan.py      # 安全扫描
└── test_coverage.sh      # 测试覆盖率报告
```

运行：
```bash
python scripts/pre_review_check.py --all
```

---

## 历史审查报告

- [2026-06-06 全量代码审查](./archive/2026-06-06-full-review.md) — 6 个严重问题，已全部修复
