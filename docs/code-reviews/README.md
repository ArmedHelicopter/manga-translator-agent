# 代码审查文档

本目录包含 Manga Translate Agent 项目的代码审查报告和工具。

## 快速开始

```bash
# 运行自动化检查
python scripts/pre_review_check.py

# 查看完整审查报告
cat docs/code-reviews/2026-06-06-full-review.md

# 查看审查检查清单
cat docs/CODE_REVIEW_CHECKLIST.md
```

## 文档结构

```
docs/
├── CODE_REVIEW_CHECKLIST.md      # 审查检查清单（用于手动审查）
└── code-reviews/
    ├── SUMMARY.md                 # 审查总结（你在这里）
    └── 2026-06-06-full-review.md  # 完整审查报告

scripts/
└── pre_review_check.py            # 自动化检查脚本
```

## 最近审查

### 2026-06-06 全量代码审查

**状态**：✅ 已完成  
**测试通过率**：99.8% (529/530)  
**修复问题**：6 个严重+高危问题  

**关键成果**：
- ✅ 修复层边界违规
- ✅ 修复批处理竞态条件
- ✅ 修复 Web API 路径泄露
- ✅ 改进 provider 异常处理
- ✅ 统一 JSON 解析逻辑
- ✅ 创建自动化检查脚本

**遗留问题**：
- ⚠️ 依赖版本不匹配（pydantic/pytest/httpx）
- ⚠️ torch 未安装（10 个测试受影响）
- ⚠️ 45 个裸异常捕获（待重构）

详见 [完整报告](../archive/2026-06-06-full-review.md)

## 自动化检查

`scripts/pre_review_check.py` 提供以下检查：

- **Layer Boundaries** — 检查跨层导入
- **Exception Hierarchy** — 检查异常使用
- **Security** — 扫描安全问题
- **JSON Parsing Consistency** — 检查统一解析器使用
- **Type Annotations** — 检查类型注解
- **Test Execution** — 验证测试可运行
- **Dependency Versions** — 检查版本一致性

### 运行所有检查

```bash
python scripts/pre_review_check.py
```

### 运行特定检查

```bash
python scripts/pre_review_check.py --check layers
python scripts/pre_review_check.py --check security
python scripts/pre_review_check.py --check tests
```

### 当前状态

```
[PASS] Layer Boundaries: CLEAN
[FAIL] Exception Hierarchy: 1 issue (translation_stage.py)
[PASS] Security: CLEAN
[FAIL] JSON Parsing Consistency: 3 issues (3 providers)
[FAIL] Type Annotations: 1 issue (cli/main.py)
[PASS] Test Execution: CLEAN
[FAIL] Dependency Versions: 3 issues (pydantic/pytest/httpx)
```

## 如何进行代码审查

### 1. 运行自动检查

```bash
python scripts/pre_review_check.py
```

### 2. 参考检查清单

打开 `docs/CODE_REVIEW_CHECKLIST.md`，逐项检查：

- [ ] 架构合规性（层边界、异常层级）
- [ ] 代码质量（类型安全、资源管理）
- [ ] 安全性（敏感信息、注入风险）
- [ ] 测试覆盖率
- [ ] 依赖管理
- [ ] 文档完备性
- [ ] 性能
- [ ] 回归测试

### 3. 运行测试

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
```

### 4. 记录发现

创建新的审查报告：

```bash
cp docs/code-reviews/2026-06-06-full-review.md \
   docs/code-reviews/$(date +%Y-%m-%d)-review.md
```

## 持续改进

### 添加新检查

编辑 `scripts/pre_review_check.py`，添加新的 `check_*` 函数：

```python
def check_new_rule(root: Path) -> CheckResult:
    """Check for new rule."""
    result = CheckResult("New Rule")
    # ... your check logic
    return result
```

### 更新检查清单

编辑 `docs/CODE_REVIEW_CHECKLIST.md`，添加新的检查项。

### 提交审查报告

```bash
git add docs/code-reviews/
git commit -m "docs: add code review report for YYYY-MM-DD"
```

## 历史记录

| 日期 | 审查者 | 问题数 | 修复数 | 报告 |
|------|--------|-------|--------|------|
| 2026-06-06 | Kiro (代理链) | 32 | 6 | [📄](../archive/2026-06-06-full-review.md) |

## 相关文档

- [CLAUDE.md](../../CLAUDE.md) — 项目架构说明
- [SPEC.md](../SPEC.md) — 功能规格
- [PRD.md](../PRD.md) — 产品需求
- [README.md](../../README.md) — 项目说明

---

**下次审查建议时间**：2026-07（1 个月后）或主要功能发布前
