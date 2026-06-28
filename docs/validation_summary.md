# Pass 1 检测参数调优验证报告

## 执行的三个任务

### 1. ✅ 集成验证已完成
**脚本**: `scripts/validate_pass1_fix.py`  
**输入**: `./data/input/私を喰べたい、ひとでなし(8).pdf`  
**输出**: `./experiments/pass1-fix-validation/.mga-payload`

**结果**:
- text_regions_count: **47**（baseline: 38，提升24%）
- fallback_count: **1**（预期0）
- fallback_page: page 10（第11页）
- 配置验证: ✅ detection_size=2560, text_threshold=0.3, box_threshold=0.5, unclip_ratio=2.5

### 2. ✅ 视觉检查已完成
**脚本**: `scripts/inspect_pass1_output.py`  
**输出**: `./experiments/pass1-fix-validation/inpainted-grid.png`

**生成文件**:
- 11张inpainted图片（inpainted-0000.png ~ inpainted-0010.png）
- 5x2缩略图网格（前10页）

### 3. ⚠️ 完整pipeline运行遇到问题
**命令**: `python -m mga.cli.main translate`  
**输出**: `./output/full-pipeline-validation/`

**问题**:
- Vision阶段失败: `ProviderError: No vision provider available` (MiMo API返回404)
- Translation阶段继续运行但因为vision失败，缺少上下文信息
- Pass 1 (export-artifact) 成功完成

## 关键发现

### 1. 检测参数已生效但效果不佳
实际使用的配置（已验证）:
```json
{
  "detector": {
    "detection_size": 2560,    // ✅ 已应用
    "text_threshold": 0.3,      // ✅ 已应用
    "box_threshold": 0.5,       // ✅ 已应用
    "unclip_ratio": 2.5         // ✅ 已应用
  },
  "inpainter": {
    "inpainter": "lama_large",  // ✅ 已应用
    "inpainting_size": 2048     // ✅ 已应用
  }
}
```

**效果对比**:
| 指标 | Baseline | Pass 1修复后 | 目标 | 达成率 |
|------|----------|-------------|------|--------|
| text_regions | 38 | **47** | ≥100 | 47% |
| fallback_count | 1 | **1** | 0 | ❌ |

**结论**: 参数调整有效（+24%），但效果远低于预期。

### 2. 每页检出分布
```
Page 0: 1 regions   (封面/版权页)
Page 1: 1 regions   (扉页)
Page 2: 16 regions  (内容页 - 最多)
Page 3: 3 regions
Page 4: 4 regions
Page 5: 3 regions
Page 6: 2 regions
Page 7: 3 regions
Page 8: 9 regions
Page 9: 5 regions
Page 10: 0 regions (fallback - 额外补偿页)
```

**观察**:
- 封面/扉页检出少（1个）符合预期
- 内容页检出仍然偏少（平均4-5个/页）
- Page 2检出16个，说明密集文字页面检出率较高

### 3. Fallback问题未解决
- PDF实际11页（不是10页）
- max_pages=10 + 补偿+1 = 处理11页
- 第11页（page_idx=10）仍然fallback，说明：
  - 可能是runtime确实只处理了10页（补偿失效）
  - 或者第11页本身就没有文字（需要人工确认）

## 可能原因分析

### 为什么text_regions只有47个？

**假设1: PDF质量问题**
- 该PDF可能是低质量扫描版
- 文字对比度低、模糊、倾斜
- 即使放宽阈值也难以检测

**假设2: 检测器模型限制**
- 使用的检测模型可能对日文漫画特殊字体支持不佳
- 艺术字、手写字、拟音效果字难以检测

**假设3: OCR模型问题**
- 使用的是48px OCR模型
- 可能对某些字号/字体的文字检出率低

**假设4: 参数仍不够激进**
- text_threshold=0.3可能还是太高
- 需要进一步降低到0.2甚至0.1

## 验证建议

### 短期验证
1. **人工抽查**：打开 `experiments/pass1-fix-validation/inpainted-grid.png`，数一下实际有多少文字气泡，看是否真的只有47个
2. **对比baseline**：找到baseline run的inpainted输出，对比第2页（16个regions）看是否确实检出更多
3. **检查mask文件**：查看 `.mga-payload/mask-*.png`，确认检测区域是否合理

### 中期优化
1. **尝试更激进的参数**：
   - text_threshold: 0.3 → 0.2
   - box_threshold: 0.5 → 0.4
   - detection_size: 2560 → 3072
2. **尝试不同的检测器**：
   - 当前使用：default (DBNet)
   - 可尝试：craft, ctd, dbconvnext
3. **尝试不同的OCR模型**：
   - 当前：48px
   - 可尝试：32px（更敏感）或manga_ocr

### 长期改进
1. **预处理增强**：在检测前对图像进行对比度增强、锐化
2. **后处理过滤**：保留检测结果，在QA阶段过滤误检
3. **多模型ensemble**：运行多个检测器，合并结果

## 下一步行动

### 立即行动
1. ✅ 打开 `experiments/pass1-fix-validation/inpainted-grid.png` 人工确认检出情况
2. ✅ 检查 `experiments/pass1-fix-validation/.mga-payload/mask-0002.png` 等mask文件
3. ⏸️ 暂缓提交代码，等待验证结果

### 如果人工验证确认检出率确实低
1. 在 `docs/experiments/registry.json` 记录此次验证结果（47 regions, 未达目标）
2. 设计 Pass 2 调优方案（更激进参数或更换检测器）
3. 重新运行 full-flow 链路

### 如果人工验证发现检出率其实合理
1. 修正预期目标（可能该PDF文字本来就少）
2. 提交Pass 1修复代码
3. 在文档中说明实际效果

## 文件清单

**已生成**:
- `./experiments/pass1-fix-validation/.mga-payload/` - Pass 1输出（47 regions）
- `./experiments/pass1-fix-validation/inpainted-grid.png` - 视觉检查网格
- `./experiments/pass1-fix-validation/.mga-payload/validation-metrics.json` - 验证指标
- `./output/full-pipeline-validation/.mga-payload/` - 完整pipeline输出（vision失败）

**待人工检查**:
- `inpainted-grid.png` - 确认是否真的只有47个文字区域
- `mask-*.png` - 确认检测区域是否合理
- `artifact-*.json` - 查看text_regions的具体内容

## 总结

✅ **已完成**:
- Pass 1参数修改并验证生效
- 集成验证脚本运行成功
- 视觉检查脚本生成网格图

⚠️ **未达预期**:
- text_regions: 47个（目标≥100，达成率47%）
- fallback仍存在（1个页面）

❓ **待确认**:
- 该PDF是否确实文字少（需要人工验证）
- 参数是否需要进一步调整
- 是否需要更换检测器模型

**建议**: 先进行人工验证，再决定是否提交代码或启动Pass 2调优。
