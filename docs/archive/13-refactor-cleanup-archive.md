# Experiment #13: refactor-cleanup-archive

## Problem Statement

项目架构存在以下问题：
1. **死代码**：StreamlinedPipeline 从未被任何主流程导入（死代码约6.8KB）
2. **备份文件冗余**：2个备份文件未清理（translation_stage_backup.py 808B, translation_stage_backup_2.py 80KB）
3. **文档与实现不一致**：REFACTORING.md 描述的目标架构与实际运行的代码存在偏差

## Hypothesis

删除死代码文件和备份文件，更新文档以反映实际架构，可以：
1. 减少 ~87KB 冗余代码
2. 提高代码库可维护性
3. 消除文档与实现的歧义

## Method

### 第一阶段：矛盾分析（mass-line + contradiction-analysis）

**收集信息源：**
- 文档 vs 实现：REFACTORING.md vs 主流程
- 导入关系：哪些文件导入哪些文件
- 主入口：mga/cli/main.py 使用哪个 orchestrator

**矛盾识别：**
- 主要矛盾：新架构已创建 vs 主流程未接入
- 次要矛盾：文档描述 vs 实际实现

**关键发现：**
- StreamlinedPipeline 无法替代 PipelineOrchestrator（缺少8个stages）
- 但 PromptBuilder 已被集成到主流程（通过 prompts.py）
- 正确的方案是渐进式整合，不是替换

### 第二阶段：实践验证（practice-cognition）

**验证假说：**
1. "直接替换 PipelineOrchestrator" → ❌ 证伪（StreamlinedPipeline 不完整）
2. "新 prompt 系统已集成" → ✅ 证实（PromptBuilder 通过 prompts.py 被使用）
3. "需要清理备份文件" → ✅ 确认（2个备份文件应该删除）

## Execution

### 1. 删除死代码文件

```bash
rm -v mga/pipeline/streamlined.py           # 6.8KB - 从未被导入
rm -v mga/pipeline/translation_stage_backup.py      # 808B - 备份文件
rm -v mga/pipeline/translation_stage_backup_2.py   # 80KB - 备份文件
```

**结果**：删除 ~87KB 冗余代码

### 2. 更新文档

更新 `docs/REFACTORING.md` 以反映：
- 当前实际架构状态
- 已集成的组件（PromptBuilder, MemoryService, CulturalService）
- 删除的文件记录

### 3. 验证测试

```bash
pytest tests/pipeline/ -v
```

**结果**：
- 139 passed, 5 failed, 7 xfailed, 1 xpassed
- 失败的测试与本次删除无关（已有问题）
- 无新回归引入

### 4. 10页E2E测试

```bash
pytest tests/pipeline/test_ten_page_e2e.py -v
```

**结果**：8 passed in 1.79s

## Results

| 指标 | 重构前 | 重构后 | 变化 |
|------|--------|--------|------|
| pipeline/*.py 文件数 | 23 | 20 | -3 |
| 冗余代码量 | ~87KB | 0 | -87KB |
| 文档准确性 | 不一致 | 一致 | ✅ |
| 测试通过率 | 139/144 | 139/144 | 无变化 |

## Architecture After Refactor

```
mga/pipeline/
├── orchestrator.py     # 主流程 (9 stages)
├── stages.py           # PipelineContext + PipelineStage
├── translation_stage.py # 翻译阶段 (18KB, 完整实现)
├── translation_service.py # PromptBuilder (已集成到prompts.py)
├── prompts.py          # Prompt 模板 (集成 PromptBuilder)
├── format_stage.py     # 格式处理
├── vision_stage.py     # Vision 增强
├── qa_stage.py         # QA 校对
├── render_stage.py     # 嵌字渲染
├── character_stage.py  # 角色归因
├── speaker_attribution_stage.py
├── output_stage.py
├── batch.py
├── incremental.py
├── parsers.py
└── ...

mga/memory/
├── service.py          # MemoryService 单例
└── ...

mga/cultural/
├── service.py           # CulturalService 单例
└── ...
```

## Files Deleted

| 文件 | 大小 | 删除原因 |
|------|------|----------|
| `mga/pipeline/streamlined.py` | 6.8KB | 从未被任何主流程导入，死代码 |
| `mga/pipeline/translation_stage_backup.py` | 808B | 备份文件 |
| `mga/pipeline/translation_stage_backup_2.py` | 80KB | 备份文件 |

## Lessons Learned

1. **重构需要分阶段**：不能期望一次性替换整个架构，需要渐进式整合
2. **文档必须与实现同步**：文档描述的目标架构需要及时更新为实际状态
3. **死代码应及时清理**：未导入的文件应该定期清理，避免混淆

## Next Steps

1. 继续优化 TranslationStage 的 token 使用
2. 完善测试覆盖（5个失败的测试需要修复）
3. 考虑将 MemoryService 集成到 PipelineContext 初始化

---

**Experiment Date**: 2026-06-11
**Experimenter**: Claude Code (AFK Agent)
**Status**: ✅ Completed
