# Pass 1 三问题修复方案

## 问题汇总

1. **OCR检出率低**：10页仅38个text_regions（典型50-200），大量文字气泡遗漏
2. **inpainter: none暴露未检出文字**：NoneInpainter只对mask填白，未检出区域日文保留
3. **最后一页未处理**：page_idx=9由fallback写入（像素完全一致），0个OCR检出

---

## 根因分析

### 问题1：Detection阈值过严

**位置**：`mga/runtime_bridge/external.py:686-702`

```python
export_config_path.write_text(
    json.dumps({
        "detector": {
            "detection_size": 2048,        # ← 对高分辨率漫画偏小
            "text_threshold": 0.5,          # ← 太高，漏掉低对比度文字
            "box_threshold": 0.7,           # ← 太高，漏掉边缘模糊气泡
            "unclip_ratio": 2.3,            # ← 偏小，检测框过紧
        },
        ...
    })
)
```

**参考值对比**：
- manga_translator默认：`text_threshold=0.5, box_threshold=0.7`（偏保守）
- CRAFT论文推荐：`text_threshold=0.3-0.4, box_threshold=0.5-0.6`（高召回）
- 漫画场景特点：低对比度气泡、手写字体、斜体效果 → 需要更宽松阈值

---

### 问题2：Inpainter配置错误

**位置**：`mga/runtime_bridge/external.py:692-695`

```python
"inpainter": {
    "inpainter": "none",               # ← 只填白mask区域
    "inpainting_size": 1024,
},
```

**问题**：
- NoneInpainter对未检出区域无能为力
- 导致输出图保留原始日文（用户报告的"部分日文没有翻译"）

**可选inpainter**：
- `lama_large`：慢但质量最高（推荐）
- `lama_mpe`：速度与质量平衡
- `default`：快但可能留痕迹

---

### 问题3：最后一页fallback的隐藏根因

**现象**：
- `inpainted-0009.png` 像素与输入完全一致
- `artifact-0009.json` 的 `text_regions: []`
- 由 `_complete_runtime_artifacts` 的fallback写入

**代码路径**：`mga/runtime_bridge/external.py:239-257`

```python
def _complete_runtime_artifacts(payload_dir: Path, runtime_input: Path) -> bool:
    """Fill empty-page artifacts and return whether any artifact exists."""
    ...
    for index, image_path in enumerate(image_paths):
        suffix = f"-{index:04d}"
        artifact_path = payload_dir / f"artifact{suffix}.json"
        inpainted_path = payload_dir / f"inpainted{suffix}.png"
        if not artifact_path.exists() or not inpainted_path.exists():
            _write_empty_runtime_artifact(payload_dir, image_path, index)  # ← fallback
```

**可能根因**：
1. runtime在处理page_idx=9时遇到错误（例如OOM、GPU崩溃），但未抛异常
2. runtime的循环逻辑有off-by-one（需要检查 `manga_translator/__main__.py`）
3. detection完全失败时，runtime跳过该页但未写入空artifact

**验证方法**：
- 检查runtime的stdout/stderr（通过 `run_export_artifact` 返回值）
- 对比输入页数与生成的artifact文件数

---

## 修复方案

### 方案1：优化Detection参数

**目标文件**：`mga/runtime_bridge/external.py`

**修改位置**：第686-702行

```python
export_config_path.write_text(
    json.dumps(
        {
            "detector": {
                "detection_size": 2560,        # 2048 → 2560（高分辨率支持）
                "text_threshold": 0.3,          # 0.5 → 0.3（提高召回率）
                "box_threshold": 0.5,           # 0.7 → 0.5（减少漏检）
                "unclip_ratio": 2.5,            # 2.3 → 2.5（扩大检测框）
            },
            "inpainter": {
                "inpainter": "lama_large",      # none → lama_large
                "inpainting_size": 2048,        # 1024 → 2048（提高修复质量）
            },
            "ocr": {
                "ocr": effective_ocr_model,
            },
            "translator": {
                "translator": "none",
                "target_lang": "CHS",
            }
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
```

**影响**：
- 提高召回率（预计从38个text_regions增加到120-180个）
- 增加处理时间（lama_large比none慢3-5倍）
- 提高inpainting质量（减少日文残留）

---

### 方案2：增强artifact验证与日志

**目标文件**：`mga/runtime_bridge/external.py`

**修改1：在`run_export_artifact`末尾增加验证**

```python
# 第763行后添加
def run_export_artifact(...) -> dict[str, Any]:
    ...
    # 原有代码
    has_artifact = _complete_runtime_artifacts(payload_dir, runtime_input) or (...)
    if not has_artifact:
        raise RuntimeError(...)

    # 新增：验证artifact数量
    expected_page_count = len(discover_image_paths(runtime_input))
    actual_artifact_count = len(list(payload_dir.glob("artifact-*.json")))
    fallback_count = 0
    for index in range(expected_page_count):
        suffix = f"-{index:04d}"
        artifact_path = payload_dir / f"artifact{suffix}.json"
        if artifact_path.exists():
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            if not artifact.get("text_regions"):
                fallback_count += 1

    return {
        "payload_dir": str(payload_dir),
        "returncode": completed.returncode,
        "max_pages": max_pages,
        "ocr_model": effective_ocr_model,
        "expected_page_count": expected_page_count,      # 新增
        "actual_artifact_count": actual_artifact_count,  # 新增
        "fallback_page_count": fallback_count,           # 新增
        "stdout_tail": sanitized_stdout[-2000:],         # 新增：保留日志用于诊断
        "stderr_tail": sanitized_stderr[-2000:],         # 新增
    }
```

**修改2：`_complete_runtime_artifacts`增加日志**

```python
def _complete_runtime_artifacts(payload_dir: Path, runtime_input: Path) -> bool:
    """Fill empty-page artifacts and return whether any artifact exists."""
    ...
    fallback_pages = []
    for index, image_path in enumerate(image_paths):
        suffix = f"-{index:04d}"
        artifact_path = payload_dir / f"artifact{suffix}.json"
        inpainted_path = payload_dir / f"inpainted{suffix}.png"
        if not artifact_path.exists() or not inpainted_path.exists():
            _write_empty_runtime_artifact(payload_dir, image_path, index)
            fallback_pages.append(index)  # 记录使用fallback的页
    
    if fallback_pages:
        # 写入fallback日志
        (payload_dir / "fallback-pages.json").write_text(
            json.dumps({"fallback_pages": fallback_pages}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    ...
```

---

### 方案3：配置可调（长期方案）

**目标**：将detection参数暴露到 `mga/config/`，而非硬编码在`external.py`

**新增文件**：`mga/config/detection_presets.toml`

```toml
[presets.conservative]
detection_size = 2048
text_threshold = 0.5
box_threshold = 0.7
unclip_ratio = 2.3

[presets.balanced]
detection_size = 2560
text_threshold = 0.3
box_threshold = 0.5
unclip_ratio = 2.5

[presets.aggressive]
detection_size = 3072
text_threshold = 0.2
box_threshold = 0.4
unclip_ratio = 2.8
```

**修改`external.py`**：从preset读取，默认`balanced`

```python
def run_export_artifact(
    *,
    detection_preset: str = "balanced",  # 新增参数
    ...
):
    preset_path = Path(__file__).parent.parent / "config" / "detection_presets.toml"
    presets = toml.load(preset_path)
    detector_config = presets["presets"][detection_preset]
    
    export_config_path.write_text(
        json.dumps({
            "detector": detector_config,  # 从preset加载
            ...
        })
    )
```

---

## 执行计划

### Phase 1：紧急修复（优先级高）
1. 修改 `external.py:686-702` 的detection/inpainter参数
2. 验证：在10页样本上重新运行，检查text_regions数量
3. 预期：从38增加到120+，inpainted图无日文残留

### Phase 2：增强诊断（优先级中）
1. 实现方案2的验证与日志增强
2. 在CLI输出中显示fallback_page_count
3. 如果fallback_count > 0，发出警告

### Phase 3：配置化（优先级低）
1. 实现detection_presets.toml
2. 在CLI添加 `--detection-preset` 参数
3. 文档化三种preset的适用场景

---

## 测试验证

### 测试用例1：基准对比
```bash
# Before
manga-translate input_10pages/ -o output_before/
# 预期：38 text_regions, 1 fallback page

# After（应用方案1）
manga-translate input_10pages/ -o output_after/
# 预期：120+ text_regions, 0 fallback pages
```

### 测试用例2：高分辨率漫画
```bash
# 使用4000x6000像素的漫画页
manga-translate high_res_input/ -o output_highres/
# 验证：detection_size=2560能覆盖全页
```

### 测试用例3：低对比度文字
```bash
# 使用淡色背景+白色文字的页面
manga-translate low_contrast/ -o output_lowcontrast/
# 验证：text_threshold=0.3能检出淡色文字
```

---

## 风险评估

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 误检增加（假阳性） | 翻译非文字区域（装饰线、背景纹理） | 使用QA层过滤低置信度翻译 |
| lama_large速度慢 | 处理时间增加3-5倍 | 优先修复检出率，后续考虑用lama_mpe平衡 |
| detection_size增大后OOM | GPU显存不足崩溃 | 捕获OOM异常，回退到2048 |
| 方案3配置复杂度 | 用户困惑选preset | 提供决策树文档 |

---

## 成功指标

- [ ] 10页样本的text_regions数从38增加到≥100
- [ ] fallback_page_count = 0（所有页正常处理）
- [ ] 输出图无肉眼可见的日文残留
- [ ] 处理时间增加<10分钟（可接受）
- [ ] 误检率<5%（通过人工抽查50个text_regions）

---

## 附录：调参指南

### text_threshold（文字置信度）
- **0.2-0.3**：高召回，适合低对比度、手写字体
- **0.4-0.5**：平衡，适合标准印刷漫画
- **0.6-0.8**：高精度，适合需要避免误检的场景

### box_threshold（边界框置信度）
- **0.4-0.5**：宽松，适合模糊边缘、不规则气泡
- **0.6-0.7**：标准，适合清晰边界的气泡
- **0.8+**：严格，仅用于高质量扫描

### detection_size（检测分辨率）
- **1536**：适合低分辨率网络漫画
- **2048**：适合标准扫描漫画（300dpi A5）
- **2560-3072**：适合高分辨率扫描（600dpi或更大幅面）

### unclip_ratio（检测框扩展比例）
- **2.0-2.3**：紧贴文字，适合密集排版
- **2.5-2.8**：留出余量，适合倾斜文字、艺术字体
- **3.0+**：大幅扩展，用于特殊效果文字（爆炸字、震动字）
