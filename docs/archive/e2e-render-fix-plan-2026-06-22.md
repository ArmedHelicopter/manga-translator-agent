# 漫画翻译管线 10 页端到端测试 — 完整修复计划

## Context（为什么做这个修复）

10 页端到端测试暴露 5 大类问题：渲染文本与 bbox 错位、翻译/QA 闲聊泄漏、inpaint 不擦字、脚注乱码/竖排错、memory 零产出。经过 5 类并行调查 + 对抗性验证（A/E 类验证器完成；B/C/D 类第一轮验证器因额度中断，我重新跑了独立对抗性验证器，全部 confirmed/高置信），并亲自逐行复核了每个根因的代码行号和证据文件。

所有根因已经**三重确认**（调查者发现 → 独立验证器反驳尝试失败 → 我亲自读代码/跑脚本复核）。验证器还纠正了调查者的若干细节，已并入本计划。

关键事实纠正（贯穿全局）：输出文件名 `page-NNN.png` 是 1-based，翻译/索引是 0-based。`page-008.png` = `page_0007.json`（索引 7）。**代码路由无 off-by-one bug**，是命名惯例陷阱。

修复执行策略：**第一波 3 个单点改动**（最高 ROI，立刻消除可见崩溃）先做，每改一个跑一次验证；**第二波**多步改动提升质量上限。代码实现委托 Haiku，code review 委托 Sonnet，我来编排和最终验证。

## 已验证根因与修复方案（按类别）

---

### 类别一：文本路由与管线状态异常

**根因 1.1（高）** — vision 气泡 `region_index` 与 OCR 区域碰撞，覆盖渲染（page-004 全气泡=第32话、page-007 标题变旁白的真因，非翻译错）
- `render_stage.py:140-181` `_page_bubble_id` 把 `region-` 和 `vision-` 两种前缀的尾号都 `int()` 成 `region_index`；vision 计数器每页从 0 重开（`vision_stage.py:357,405`）
- `translations-0003.json` 实测 region_index 0 和 1 各出现两次；运行时 `manga_translator.py:721-725` 后写覆盖 → 第32话盖掉正文
- **修复**：`render_stage.py:166-181` 只对 `region-` 前缀的气泡发 `region_index`，跳过 `vision-` 前缀；读 `artifact-NNNN.json` 的 `len(text_regions)`，跳过越界 index，对重复 region_index 告警

**根因 1.2（高）** — OCR 漏检的页面视觉翻译无 bbox 座位 → 近原图输出（page-010、page-003）
- page-010：`artifact-0009.json` text_regions=[]，无 mask，8 条翻译全被丢弃
- **修复**：`manga_translator.py:721-725` 或 `rendering/__init__.py` 当 translations 非空但 text_regions 空时 warning

**根因 1.3（高）** — 视觉气泡有翻译但运行时 artifact 无 bbox 座位，无处渲染
- vision 气泡有 host 端 bbox（`vision_stage.py:362-393` 保留了 `raw_bbox`/`bbox`），但 artifact 只含 OCR 区域
- **修复**（较大，第二波）：`_complete_runtime_artifacts`/`_write_page_translations` 把视觉气泡的 bbox 注入 artifact `text_regions`，或 host 端 post-render overlay

---

### 类别二：翻译引擎与上下文识别

**根因 2.1（高）** — "往昔の足音→令人悲伤的是" 是渲染错位（同 1.1），非误译。page_0006 翻译正确，旁白 region_index=0 盖掉标题 region_index=0。修 1.1 即解。

**根因 2.2（高）** — "うん 未翻译" 是渲染丢弃（同 1.2/1.3），非翻译漏。page_0009 有全部 8 条翻译，0 OCR 区域全丢。修 1.2/1.3 即解。

**根因 2.3（高，验证器范围扩展）** — QA re-translate + 主翻译路径对话泄漏
- `qa_stage.py:199-216` `call_chat`（无 schema/无解析）返回值 `raw.strip()` 直接赋 `candidate.text`
- **验证器纠正**：泄漏**不只 QA 路径**——`page_0002.json region-0002-0006` rationale 是 `persona-render`（主翻译路径）却含"您好！我已经了解了…"泄漏。主路径 `_clean_translation_text` 也漏掉中文对话体
- `render_stage._extract_render_text` 只认 JSON/≤24 字符尾部括注，对纯散文无效
- **修复**：① `qa_stage.py:210-216` 改 `call_chat_structured` + schema `{text:string}`，extract `text` 后过 `_clean_translation_text`；JSON 解析失败 fallback `parse_jsonish_response`+`_clean_translation_text`，**不存 raw.strip()** ② `qa_stage.py:199` source_text 空时跳过重翻译 ③ `render_stage.py:304-305` 加对话标志检测 leak guard（`您好|已根据源文修正|请您提供|以JSON格式|修正后的简体中文`）回退前次 clean 候选 ④ `parsers.py:35-56` `_clean_translation_text` 加中文对话前缀/后缀模式 ⑤ `tests/pipeline/test_qa_stage.py` 加 FakeProvider 返回对话泄漏的测试

**根因 2.4（高，次要）** — `source_text` 空时回退坏译文当源文（`qa_stage.py:199`）。验证器指出对观察到的泄漏条目（source 非空）未触发，是次要诱因但仍真 bug。修 ② 已含。

---

### 类别三：图像清理/抹图失效

**根因 3.1（高）** — Pass 1 用不重建 inpainter
- 磁盘 `runtime-export-config.json`=`none`；`none.py:10-12` 涂白；`original.py:9-10` 透传；`external.py:726` 现源码 auto→`original`（更糟）
- `LamaLargeInpainter` 存在（`inpainting_lama_mpe.py:121`），`InpainterConfig` 默认 `lama_large`
- **修复**：`external.py:726` auto→`lama_large`；更新 stale docstring（687-689 说 auto→none，实际 auto→original）

**根因 3.2（高，验证器数值纠正）** — 掩码膨胀成整块
- `bubble_mask_enlarge_ratio` 运行时是 **5.0**（`config.py:348` InpainterConfig 默认），非调查者说的 1.6（1.6 是 `dispatch()` 函数签名默认，被 5.0 覆盖）。膨胀比报告的更严重
- `mask_dilation_offset=20`；8 列竖排窄标题 + 5.0 倍膨胀 → 并成 27.8% 整块
- **修复**（第二波，defense-in-depth）：mask 覆盖 >阈值（如 15% 页面）时限制 `bubble_mask_enlarge_ratio`/`mask_dilation_offset`

**根因 3.3（高）** — page-008/009 鬼影 = none 不擦 + 掩码未全覆盖。修 3.1 即解。

---

### 类别四：渲染乱码与竖排

**根因 4.1（高，验证器纠正我）** — 脚注用硬编码 Linux 字体 → `load_default()` → Windows tofu
- `manga_translator.py:786-792` 只试 2 个 Linux Noto 路径 → `load_default()`
- **验证器纠正**：`fonts/msyh.ttc` **在 repo 根目录**（19.6MB），气泡渲染器 `FALLBACK_FONTS`（`text_render.py:210-214`）已在用。我早先 `find manga_translator -name "*.ttc"` 漏了 repo 根
- **修复**：`manga_translator.py:786-792` 用 `os.path.join(BASE_PATH,'fonts/msyh.ttc')`→`Arial-Unicode-Regular.ttf`→`msgothic.ttc`→`C:/Windows/Fonts/msyh.ttc`→Linux Noto→`load_default()`

**根因 4.2（高）** — CJK_H2V 缺全角 `？`/`！`
- `text_render.py:89-93` 有半角 `?`→`︖`、`!`→`︕`，缺全角 `？`(U+FF1F)、`！`(U+FF01)。msyh.ttc 有这些字形
- **修复**：`text_render.py:89-93` 加 `"？":"︖"`、`"！":"︕"`

**根因 4.3（高，验证器纠正调查者）** — `…`→`⋮` 映射错误
- 第 72 行 `…`(U+2026)→`⋮`(U+22EE)，msyh.ttc 无 U+22EE，fallback 到 Arial-Unicode 细数学省略号（乱码样）
- **验证器纠正**：第 73 行 `⋯`(U+22EF)→`︙`(U+FE19) 正确，msyh.ttc 有 U+FE19。第 72 行应改成 `…`→`︙`(U+FE19)
- **修复**：`text_render.py:72` `"…": "⋮"` → `"…": "︙"`（一行字符改，无需改字体）

---

### 类别五：memory 零产出

**根因 5.1（高）** — 冷启动角色归因只匹配不创建。`speaker_attribution_stage.py:129-137` 候选空 → `:121-127`/`:82-91` 全拒，无创建路径
**根因 5.2（高，验证器纠正内存位置）** — `translation_stage.py:422` `speaker=bubble.speaker_id or ""`，`:589` `if speaker` 短路。验证器：`config/loader.py:192` working_dir=输入目录，memory 写到 `data/input/test-pdf-10pages/memory/`（`character_graph.json={"nodes":[],"edges":[]}` 证实初始化了但无实体）
**根因 5.3（高）** — `character_stage.py:29-31,50-56` bootstrap 依赖 `external-baseline-text-normalized.json`，external-two-pass 不生成 → 种子永不运行
**根因 5.4（中）** — mimo 视觉模型没输出 `provisional_speaker`（`page_0008.json` 9 气泡三字段全 null）。需查原始 mimo 响应定是模型没输出还是解析丢弃

**修复**（第二波）：① 查 mimo vision 为何无 `provisional_speaker`（prompt/schema/解析）② `speaker_attribution_stage.py:121-127` 有 hint 但候选空时自动创建角色 ③ `translation_stage.py:422,589` 兜底派生 `speaker = ... or f"char_p{page}_{idx}"`（可配开关）④ `character_stage.py:29-31` 加 `.mga-payload/artifact-*.json` 作种子源

---

## 实施计划

### 第一波：3 个单点改动（最高 ROI，立刻消除可见崩溃）

每改一个跑一次验证。代码实现委托 Haiku。

#### 改动 1：修复 region_index 碰撞（类别 1.1）— 委托 Haiku
**文件**：`mga/pipeline/render_stage.py`
**位置**：`_write_page_translations`（124-260），核心 166-181
**改法**：
1. 只对 `region-` 前缀的 bubble 发 `region_index`；`vision-` 前缀的 bubble **跳过**（不加入 translations 列表），因为运行时 artifact 无其 bbox 座位
2. 读 `artifact-NNNN.json` 的 `text_regions` 数量（payload_path 可用），跳过 `region_index >= len(text_regions)` 的条目，log warning
3. 对重复 `region_index` 告警（不覆盖——保留第一个 OCR 区域的翻译）
**验证**：`translations-0003.json` 不再有重复 region_index；page-004 输出每个 OCR 区域显示自己的翻译而非全"第32话"
**注意**：vision 气泡暂时不渲染（直到第二波 1.3 落地），但严格好于当前盖错 OCR 座

#### 改动 2：脚注用 CJK 字体（类别 4.1）— 委托 Haiku
**文件**：`manga_translator/manga_translator.py`
**位置**：`_draw_footnotes` 786-792
**改法**：替换 2 个 Linux Noto 路径为字体链：`os.path.join(BASE_PATH,'fonts/msyh.ttc')`→`fonts/Arial-Unicode-Regular.ttf`→`fonts/msgothic.ttc`→`C:/Windows/Fonts/msyh.ttc`→Linux Noto→`load_default()`
**验证**：脚注不再乱码（用有脚注的页跑一次）

#### 改动 3：inpainter 改 lama_large（类别 3.1）— 委托 Haiku
**文件**：`mga/runtime_bridge/external.py`
**位置**：726 行 + docstring 687-689
**改法**：`effective_inpainter = "lama_large" if inpaint_backend == "auto" else inpaint_backend`；更新 docstring 说 auto→lama_large
**验证**：page-003 不再白页（lama 重建背景）；需下载 ~200MB 模型权重，首次跑慢

第一波后跑 10 页端到端验证，确认 page-004/007 文本正确、脚注不乱码、page-003 不白。

### 第二波：多步改动（提质量上限）

#### 改动 4：QA 重翻译结构化 + leak guard（类别 2.3/2.4）— 委托 Haiku
- `mga/pipeline/qa_stage.py:210-216` 改 `call_chat_structured` + schema `{type:object, properties:{text:{type:string}}, required:[text]}`，extract `text` 后过 `_clean_translation_text`；JSON 解析失败 fallback `parse_jsonish_response`+`_clean_translation_text`；不存 raw.strip()
- `qa_stage.py:199` source_text 空时跳过重翻译
- `render_stage.py:304-305` 加对话标志 leak guard，回退前次 clean 候选
- `parsers.py:35-56` `_clean_translation_text` 加中文对话前缀/后缀模式（`已根据源文修正`、`您好`、`请您提供`、`以JSON格式`、`修正后的简体中文` 等）
- `tests/pipeline/test_qa_stage.py` 加 FakeProvider 返回对话泄漏的测试
**验证**：`vision-0003-0020` source "169" → text "169"（非对话泄漏）；跑现有 qa 测试

#### 改动 5：memory 冷启动链（类别 5.1-5.4）— 委托 Haiku
- 查 mimo vision 无 `provisional_speaker` 根因（`vision_stage.py:43,324-345` + `mimo_provider.py`）
- `speaker_attribution_stage.py:121-127` 有 hint 但候选空时自动创建角色
- `translation_stage.py:422,589` 兜底派生 speaker（可配开关）
- `character_stage.py:29-31` 加 `.mga-payload/artifact-*.json` 作种子源
**验证**：跑后 `memory/state/characters/*.json` 非空；speaker 非全 null

#### 改动 6：CJK_H2V 全角标点 + `…` 映射（类别 4.2/4.3）— 委托 Haiku
- `manga_translator/rendering/text_render.py:89-93` 加 `"？":"︖"`、`"！":"︕"`
- `text_render.py:72` `"…":"⋮"` → `"…":"︙"`
**验证**：竖排气泡全角 `？`/`！` 旋转；`…` 不再乱码

#### 改动 7：mask 膨胀阈值（类别 3.2）— 委托 Haiku
- `manga_translator/mask_refinement/__init__.py:644-660` mask 覆盖 >15% 页面时限制 `bubble_mask_enlarge_ratio`/`mask_dilation_offset`
**验证**：page-003（目录页）掩码不再并成整块

#### 改动 8：视觉气泡 bbox 注入（类别 1.2/1.3）— 委托 Haiku
- `_complete_runtime_artifacts`/`_write_page_translations` 把视觉气泡 bbox 注入 artifact `text_regions`，或 host 端 post-render overlay
**验证**：page-010 视觉翻译渲染出来（不再近原图）

### Code Review（委托 Sonnet）
每波改完后，派 Sonnet agent 做 code review：检查改动是否引入回归、是否遵循现有 pattern、是否漏改关联点。我整合 review 结果后决定是否修。

## 验证计划

1. **单元/集成测试**：`pytest tests/ -v`（985 passing baseline，不破坏）
2. **改动 1 验证**：检查 `translations-0003.json` 无重复 region_index；读 page-004 输出
3. **改动 2 验证**：跑有脚注的页，脚注不乱码
4. **改动 3 验证**：page-003 不白页；`runtime-export-config.json` 显示 lama_large
5. **端到端**：重跑 10 页测试，对比输出
6. **回归**：所有现有测试通过

## 不修复的项（记录）
- 调查者/验证器确认 page-003 白底主因是 inpaint（类别 3），非路由（类别 1）—— 已归入 3.1
- `bubble_mask_enlarge_ratio` 5.0 vs 1.6 的差异不影响根因，3.2 修复仍适用
- mimo vision 无 speaker 是上游触发器（5.4），需单独查原始响应
