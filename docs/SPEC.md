# Manga Translation Agent — SPEC v0.4

> 状态：设计草案
> 日期：2026-05-05
> 版本：v0.5（整合日语专家反馈：管理元数据、关系图谱强化、敬语多维补偿、QA优先级重排）
> 作者：奏同学 + Hermes Agent

---

## 0. 市场调研与痛点分析

### 0.1 现有产品全景

#### 开源方案

| 项目 | ⭐ | 架构 | 嵌字 | CLI/Agent | 许可证 |
|------|-----|------|------|-----------|--------|
| **manga-image-translator** | 9845 | CRAFT检测→manga-ocr→LaMa擦除→20+翻译引擎→自研嵌字 | ⭐⭐⭐ | ✅ CLI+API+Docker | GPL-3.0 |
| **BallonsTranslator** | 4762 | 复用manga-image-translator底层，PyQt6 GUI | ⭐⭐⭐⭐(GUI辅助) | ⚠️ headless模式 | GPL-3.0 |
| **koharu** | 4276 | Rust+candle本地推理，Tauri桌面 | ⭐⭐⭐ | ✅ HTTP API + MCP Server | GPL-3.0 |
| **comic-translate** | 2682 | RT-DETR检测→多语言OCR→LaMa→LLM翻译 | ⭐⭐⭐ | ❌ 仅GUI | Apache-2.0 |
| **manga-ocr** | 2639 | ViT日文OCR（被上面全部依赖） | — | ✅ Python包 | Apache-2.0 |

#### 闭源方案

| 类别 | 代表 | 价格 | 特点 |
|------|------|------|------|
| 官方平台 | Manga Plus (集英社), Shonen Jump/VIZ | 免费/$1.99/月 | 官方翻译质量最高，但仅限授权作品 |
| 云API | Google Cloud Vision+Translation, Azure AI, AWS | 按量计费 | 底层能力顶尖，但无端到端封装 |
| 桌面工具 | Cotoha | 企业级定价 | 日语NLP专精，个人用户难以负担 |
| 浏览器插件 | Chrome Manga Translator | 免费 | 实时在线翻译，质量一般 |
| CAT工具 | memoQ, SDL Trados | $300-1500/年 | 面向专业译者，非漫画专用 |
| 韩国平台 | Webtoon, Kakao, Lezhin | 平台内建 | 翻译团队内化，不对外开放工具 |

### 0.2 痛点分析

现有方案的**结构性缺陷**，不是小修小补能解决的：

**P1: OCR pipeline 信息逐级丢失**
```
现状：图片 → OCR文本 → 翻译 → 嵌字
      每一步都是有损操作，错误级联传播
```
OCR 只提取文字，丢失了：谁在说（角色归属）、怎么说（情绪/语气）、为什么说（叙事上下文）、画面在讲什么（视觉叙事）。翻译阶段拿到的是剥离了全部上下文的纯文本，只能靠猜测补回丢失的信息。

**P2: 角色语言一致性为零**
现有方案对所有角色使用同一套翻译策略。没有角色档案，没有口癖追踪，没有称呼体系管理。雨宫灯对师傅和对同门的翻译腔调完全一样——这在漫画翻译中是致命的。

**P3: 嵌字是最大短板**
开源方案的嵌字效果：日漫竖排尚可，横排偶有问题，西式漫画拉胯，复杂背景补丁感强。根本原因是擦除质量不够——LaMa 在复杂场景下留痕明显，后续嵌字无法补救。

**P4: 虚构文字无人处理**
咒术回战的咒语、来自深渊的深渊文字、海贼王的历史正文——现有工具要么 OCR 出乱码，要么直接报错。没有方案处理虚构书写系统。

**P5: 文化适配为零**
作者造词（硝子継ぎ）、文化独有概念（木漏れ日）、敬语系统——现有方案全部忽略，直译了事。漫画的文化层被完全压平。

**P6: 闭源方案要么太贵要么太窄**
- 云API：能力强但需要自己搭 pipeline，无端到端产品
- 官方平台：质量高但只有正版授权内容
- 付费桌面工具：企业级定价，个人用户用不起
- 浏览器插件：仅限在线漫画，不支持本地文件

**P7: 格式支持碎片化**
- manga-image-translator：只支持图片目录
- comic-translate：支持 PDF/EPUB/CBR/CBZ 但仅 GUI
- 没有 CLI 工具同时支持 图片 + EPUB + MOBI + PDF + CBR/CBZ

**P8: 无增量翻译能力**
所有方案都是从头处理。漫画连载场景下，每次出新话需要：加载前文角色档案、保持翻译一致性、检测角色语言演化——没有方案做到。

**P9: 供应商锁定**
现有方案绑定单一翻译引擎或单一模型。无法根据成本、质量、隐私需求灵活切换云端/本地模型。

### 0.3 我们的定位

```
现有方案：工具链（pipeline of tools）
我们的方案：Agent（具备记忆、推理、校对能力的智能体）

差异不是功能多少，是架构层级不同：
- 工具：输入→处理→输出，无状态
- Agent：输入→理解→推理→校对→输出，有记忆、有角色认知、有质量意识
```

### 0.4 从 Translation Pipeline 到 Character Simulation System

`mga` 不是传统意义上的漫画翻译器，而是一个在画面、文化与人物关系约束下，生成角色一致性对白的系统。

传统翻译引擎主要处理的是语言映射：把一句日文变成一句中文。`mga` 处理的则是人格模拟与关系约束下的语言生成：

> 这个角色，在这个章节阶段，面对这个对象，带着这种情绪和权力关系，会如何用目标语言说这句话？

因此系统优化目标不只包括译文正确性，还包括：

- 角色人格在连续章节中的稳定性
- 对不同对象的称呼、敬语与语气切换
- 情绪推进与语言演化是否符合角色轨迹
- 文化与视觉上下文是否被保留到对白生成中

核心差异化价值：
1. **角色一致性**——系统目标是人格稳定，而不是单句自然
2. **关系约束**——RAG 驱动的角色档案 + 图模型的关系图谱共同约束语言生成
3. **翻译学习引擎**——有已有翻译就从中学习，热启动永远优先于冷启动
4. **校对层**——独立 QA Stage，不只纠错，也审查人设漂移与关系失真
5. **Vision-first**——保留画面、叙事与说话场景，作为人格模拟的感知基础
6. **文化适配层**——术语库 + 文化词汇分级策略 + 作者造词自动发现
7. **格式全支持**——输入/输出均支持图片/EPUB/MOBI/PDF/CBR/CBZ
8. **供应商自由**——云端/本地模型随意切换，无锁定
9. **增量翻译**——支持连载场景的上下文保持和角色演化追踪

### 0.5 Why External-First

`mga` 当前不把“完全替代现有漫画翻译 runtime”作为近期工程目标，而采用 external-first 路线：

- 复用成熟 runtime 负责检测、OCR、擦字、嵌字与基础页级翻译
- 由 `mga` 负责 orchestration、benchmark、review、artifacts 与 intelligence
- 先证明“角色一致性生成 + 可审查工程能力”能创造明显价值，再决定是否需要更深的 runtime 替换

因此近期的关键判断不是：

> internal runtime 能不能立刻比 external 更强

而是：

> `mga` 能不能在 external runtime 之上，建立可审查、可学习、可校准的 intelligence layer

---

## 1. 概述

一个基于多模态 LLM 的漫画翻译 agent，完成从原图到翻译嵌字成品的全流程。近期的推荐落地方式不是推倒重写整条链路，而是以 external runtime 为宿主，以 `mga` 的结构化中间层和 intelligence layer 为差异化主线。

它的最终目标不是“把每个气泡翻对”，而是“让角色在目标语言里依然像他自己说话”。译文准确性仍然重要，但它只是人格一致性系统的基础条件，而不是全部目标。

### 设计原则

1. **角色一致性优先**：单句正确是底线，角色稳定才是目标
2. **Vision-first**：多模态模型是主干，OCR 是 fallback
3. **角色即知识**：角色语言档案通过 RAG 注入，不是硬编码在 prompt 里
4. **关系即约束**：人物关系不是背景资料，而是对白生成约束
5. **文化即层次**：文化词汇分级处理，不硬译不回避
6. **反幻觉优先**：每条翻译必须锚定到具体气泡，修改必须带理由
7. **供应商自由**：云端/本地模型可选，无锁定
8. **格式无关**：输入输出格式不影响翻译质量
9. **渐进式智能**：先跑通基础流程，再叠加角色档案、关系图等增强层
10. **学习优先**：有已有翻译就从中学习，没有就从零建立——热启动永远优先于冷启动
11. **runtime 与 intelligence 解耦**：成熟 runtime 可复用，真正的产品护城河应落在 intelligence layer

### 1.1 Three-Layer Architecture

当前推荐架构分三层：

1. **external runtime layer**
   - 检测
   - OCR
   - 擦字 / 嵌字
   - 页级翻译底盘
   - 近期正式宿主：`manga-image-translator`
2. **mga orchestration layer**
   - artifact store
   - benchmark / review
   - provider routing
   - run control
   - CLI 与批处理脚本
3. **mga intelligence layer**
   - 角色一致性翻译
   - `learn-from`
   - QA
   - 关系约束
   - 人格校准

近期默认语义：

- `external-first delivery path`：唯一正式产品主线
- `internal`：历史验证资产与参考实现，不再作为产品实现路线继续推进

`internal` 可以保留代码与文档参考价值，但不再承担任何近期产品交付承诺。

### 启动模式

```
用户输入：
├── 漫画文件（待翻译）
└── （可选）已有翻译文件（已翻译的同作品章节）

判断逻辑：
if 已有翻译文件:
    → 热启动（Warm Start）
    → 运行翻译学习引擎（§8.4）
    → 自动生成角色档案 + 术语库 + 风格指南
    → 用学习结果翻译新文件
else:
    → 冷启动（Cold Start）
    → Vision Stage 自动发现角色和术语
    → 边翻译边建立档案
    → 后续章节逐步完善
```

```bash
# 热启动：有已有翻译
manga-translate new_chapters/ --learn-from existing_translations/ -o output/

# 冷启动：没有已有翻译
manga-translate input/ -o output/

# 混合：用已翻译的前10话学习，翻译第11-20话
manga-translate ch11_to_20/ --learn-from ch01_to_10_translated/ -o output/

# 只学习不翻译：生成角色档案和术语库
manga-translate --learn-only existing_translations/ --output-profiles profiles/
```

---

## 2. 供应商架构

### 2.1 设计目标

- 每个 Stage 可独立选择供应商
- 支持云端 API 和本地模型混合使用
- 供应商切换不需要修改业务代码
- 自动 fallback（主供应商不可用时切换备选）
- 能支撑 external-first runtime 改造链路；internal 只保留历史 benchmark 与参考价值

### 2.1.1 Runtime Strategy

近期实现上只保留一条正式产品线：

- **external runtime path**
  - 让 `manga-image-translator` 作为正式宿主产出页级与区域级文本
  - 再接入 `mga` 的 benchmark、review、QA、memory wiki 与后续 translation brain

`internal structured path` 已降级为 legacy research path，只通过 `legacy` 命令空间暴露。

### 2.2 供应商抽象层

```python
class LLMProvider(ABC):
    """LLM 供应商基类"""

    @abstractmethod
    def chat(self, messages: list[dict], **kwargs) -> str:
        """发送聊天请求，返回文本响应"""
        ...

    @abstractmethod
    def chat_structured(self, messages: list[dict], schema: dict, **kwargs) -> dict:
        """发送聊天请求，返回结构化 JSON"""
        ...

    @abstractmethod
    def vision(self, messages: list[dict], images: list[bytes], **kwargs) -> str:
        """多模态请求（文本+图片）"""
        ...

    @abstractmethod
    def vision_structured(self, messages: list[dict], images: list[bytes],
                          schema: dict, **kwargs) -> dict:
        """多模态结构化请求"""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @property
    @abstractmethod
    def supports_vision(self) -> bool: ...

    @property
    @abstractmethod
    def cost_per_1k_tokens(self) -> float: ...
```

### 2.3 已实现供应商

#### 云端供应商

| 供应商 | 实现类 | Vision | 结构化输出 | 适用 Stage |
|--------|--------|--------|-----------|-----------|
| OpenAI | `OpenAIProvider` | ✅ (GPT-4o) | ✅ JSON mode | Vision, Translation, QA |
| Anthropic | `AnthropicProvider` | ✅ (Claude) | ⚠️ 手动解析 | Translation, QA |
| Google Gemini | `GeminiProvider` | ✅ (2.5 Pro/Flash) | ✅ JSON mode | Vision, Translation, QA |
| DeepSeek | `DeepSeekProvider` | ❌ | ✅ JSON mode | Translation, QA |
| OpenRouter | `OpenRouterProvider` | ✅ (取决于模型) | ✅ | 全部（统一入口） |

#### 本地供应商

| 供应商 | 实现类 | Vision | 结构化输出 | 部署方式 |
|--------|--------|--------|-----------|---------|
| Ollama | `OllamaProvider` | ✅ (LLaVA/Qwen2-VL) | ⚠️ 手动解析 | `ollama serve` |
| LM Studio | `LMStudioProvider` | ✅ (取决于模型) | ⚠️ 手动解析 | `lms server start` |
| vLLM | `VLLMProvider` | ✅ (需多模态模型) | ✅ OpenAI 兼容 | `vllm serve` |
| llama.cpp | `LlamaCppProvider` | ❌ (纯文本) | ⚠️ | `llama-server` |

### 2.4 配置

```toml
# providers.toml

[stages.vision]
primary = "openai"          # GPT-4o
fallback = "gemini"         # Gemini 2.5 Pro
local = "ollama"            # Ollama + Qwen2-VL (离线时用)

[stages.translation]
primary = "openai"          # GPT-4o-mini
fallback = "deepseek"       # DeepSeek V3 (便宜)
local = "ollama"            # Ollama + Qwen2-7B

[stages.qa]
primary = "openai"          # GPT-4o (推理能力)
fallback = "anthropic"      # Claude Sonnet
local = "lmstudio"          # LM Studio + 本地模型

[providers.openai]
api_key = "${OPENAI_API_KEY}"
base_url = "https://api.openai.com/v1"

[providers.gemini]
api_key = "${GEMINI_API_KEY}"

[providers.deepseek]
api_key = "${DEEPSEEK_API_KEY}"
base_url = "https://api.deepseek.com/v1"

[providers.ollama]
base_url = "http://localhost:11434"
vision_model = "qwen2-vl:7b"
text_model = "qwen2:7b"

[providers.lmstudio]
base_url = "http://localhost:1234/v1"
model = "local-model"

[providers.vllm]
base_url = "http://localhost:8000/v1"
model = "Qwen/Qwen2-VL-7B-Instruct"
```

### 2.5 供应商选择策略

```python
# 每个 Stage 的供应商选择逻辑
def select_provider(stage: str, config: dict, force_local: bool = False) -> LLMProvider:
    stage_config = config["stages"][stage]

    if force_local:
        return get_provider(stage_config["local"])

    try:
        return get_provider(stage_config["primary"])
    except ProviderUnavailable:
        try:
            return get_provider(stage_config["fallback"])
        except ProviderUnavailable:
            return get_provider(stage_config["local"])
```

当前 CLI 语义：
```bash
# 默认产品主链：external-core runtime
manga-translate input/ -o output/

# 正式 external 对比与归一化报告
manga-translate benchmark-external input/ -o output/

# legacy 提取/翻译研究链
manga-translate legacy benchmark-extraction input/ -o output/
```

---

## 3. 格式支持

### 3.1 输入格式

| 格式 | 扩展名 | 处理方式 |
|------|--------|---------|
| **图片** | `.jpg` `.jpeg` `.png` `.webp` `.bmp` `.tiff` | 直接送 Vision Stage |
| **PDF** | `.pdf` | 逐页提取为图片（PyMuPDF/Poppler） |
| **EPUB** | `.epub` | 解压→提取 XHTML 中的图片→翻译→重新打包 |
| **MOBI/AZW** | `.mobi` `.azw` `.azw3` | 转换为 EPUB 后处理 |
| **CBR/CBZ** | `.cbr` `.cbz` | 解压（RAR/ZIP）→图片目录→翻译→重新打包 |
| **目录** | 路径 | 按文件名排序的图片集合 |

### 3.2 输出格式

| 输出格式 | 说明 | 适用场景 |
|---------|------|---------|
| **图片目录** | `output/` 下按页存放翻译后图片 | 默认输出，通用 |
| **PDF** | 翻译嵌字后的 PDF | 打印、归档、分享 |
| **EPUB** | 翻译后的 EPUB（保留原始结构） | 电子书阅读器 |
| **CBZ** | 翻译后的 CBZ（图片压缩包） | 漫画阅读器（Komga, Kavita） |
| **双语对照** | 左页原文/右页译文的 PDF | 学习、校对 |
| **翻译报告** | JSON/YAML 格式的完整翻译记录 | 开发者、批量处理 |

```bash
# 默认：图片目录
manga-translate input.pdf

# 指定输出格式
manga-translate input.pdf -o output.pdf --format pdf
manga-translate input/ --format epub -o translated.epub
manga-translate input.cbr --format cbz -o translated.cbz

# 双语对照模式
manga-translate input.pdf --format bilingual -o bilingual.pdf

# 导出翻译报告（不含图片，只含翻译数据）
manga-translate input/ --format report -o report.json
```

### 3.3 FormatAdapter 接口

```python
class FormatAdapter(ABC):
    """格式适配器基类（输入+输出统一）"""

    @abstractmethod
    def extract(self, input_path: Path) -> Iterator[PageRef]:
        """提取页面，返回页面引用迭代器"""
        ...

    @abstractmethod
    def repack(self, pages: Iterator[TranslatedPage], output_path: Path):
        """将翻译后的页面重新打包为输出格式"""
        ...

@dataclass
class PageRef:
    index: int
    image_path: Path
    original_ref: str
    metadata: dict

@dataclass
class TranslatedPage:
    index: int
    image_path: Path
    page_json: dict
    qa_report: dict
```

### 3.4 格式处理细节

**PDF**：
- 输入：PyMuPDF 逐页渲染 300DPI
- 输出：图片 PDF 或保留原结构（取决于输入类型）
- 扫描件 vs 数字 PDF 自动检测

**EPUB**：
- 输入：解压 → 解析 OPF 获取 spine → 提取 XHTML 中的 <img>
- 输出：替换图片 → 更新 OPF → 重新打包
- 保留 CSS 和元数据

**MOBI/AZW3**：
- 依赖 Calibre `ebook-convert` 转为 EPUB
- 未安装 Calibre 时拒绝处理并提示

**CBR/CBZ**：
- CBR 需要 `unrar`，CBZ 用 Python `zipfile`
- 文件名自然排序（page1, page2, ..., page10）

---

## 4. 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    用户输入层                              │
│  输入：漫画文件 + 项目元数据 + 供应商配置                    │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              Stage 0: 格式解析（Format Stage）              │
│  FormatAdapter → PageRef 迭代器                            │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              Stage 1: 全页视觉理解（Vision Stage）          │
│  多模态 LLM → Page JSON                                    │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│           Stage 2: 角色归属 + 文化适配                      │
│  角色图谱 RAG + 术语库检索 + 文化词汇分类                    │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│            Stage 3: 语境化翻译（Translation Stage）         │
│  LLM 逐气泡翻译（携带角色档案+文化上下文）                    │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│           Stage 4: 校对与一致性检查（QA Stage）              │
│  独立 LLM 校对（事实+角色+情绪+文化）                        │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│            Stage 5: 擦除与嵌字（Rendering Stage）           │
│  LaMa 擦除 + 字体选择 + 排版 + 渲染                        │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              Stage 6: 格式输出 + 人工审查                    │
│  FormatAdapter.repack() + QA Report                       │
└─────────────────────────────────────────────────────────┘
```

---

## 5. 数据结构

### 5.1 Page JSON（Stage 1 输出）

```json
{
  "page_id": "ch023_p008",
  "chapter": 23,
  "page": 8,
  "panels": [
    {
      "panel_id": "p1",
      "bbox": [0, 0, 540, 500],
      "scene_description": "灯跪在碎裂的硝子堆中，冰室倒在一旁，的場站在门口冷眼旁观",
      "characters": [
        {
          "visual_id": "char_1",
          "name_hint": "深蓝短发少年，戴工匠护目镜",
          "position": "center",
          "emotion": "恐惧转愤怒",
          "body_language": "跪地，手握碎硝子割伤流血"
        },
        {
          "visual_id": "char_2",
          "name_hint": "银白长发少年，倒在地上",
          "position": "right",
          "emotion": "无意识",
          "body_language": "仰躺，胸口有碎硝子刺入"
        }
      ],
      "bubbles": [
        {
          "bubble_id": "p1_b1",
          "bbox": [50, 30, 300, 120],
          "speaker_hint": "char_1",
          "bubble_type": "shout",
          "script_type": "standard_jp",
          "text_jp": "氷室——！！誰か、誰か呼んでくれ！！",
          "text_context": "灯发现冰室重伤，第一次失去冷静",
          "needs_translation": true
        }
      ],
      "sfx": [
        {
          "sfx_id": "p1_s1",
          "bbox": [350, 200, 480, 280],
          "text_jp": "ガシャン",
          "sfx_type": "impact",
          "visual_role": "硝子碎裂的回响",
          "needs_translation": true
        }
      ]
    }
  ],
  "coined_terms": [
    {
      "term_jp": "硝子継ぎ",
      "context": "灯的独有工匠技艺，将碎裂的硝子重新熔接",
      "structural_hint": "硝子+継ぎ（接合）",
      "frequency": "recurring",
      "suggested_strategy": "literal"
    }
  ],
  "cultural_terms": [
    {
      "term_jp": "硝子師の心得",
      "context": "角色回忆师傅教授的工匠行话",
      "cultural_weight": "high",
      "suggested_strategy": "preserve_or_coined"
    }
  ],
  "narrative_summary": "冰室在硝子工坊事故中重伤，灯首次失控，的場冷漠旁观暴露其真实面目",
  "page_mood": "crisis",
  "contains_fictional_script": false,
  "pure_visual_pages": false
}
```

### 5.2 角色档案（Character Profile）

```toml
# character_profiles/glass_and_blade/amamiya_akari.toml
# 以下为虚构作品「硝子と刃」的示例角色档案

[meta]
name_jp = "雨宮 灯"
name_zh = "雨宫灯"
first_appearance = "ch001_p023"
archetype = "内向型天才工匠"

[meta.provenance]
# 管理性元数据：档案的创建、审核、溯源信息
created_by = "learning_engine_v0.3"       # 谁创建的（AI版本/译者名）
created_at = "2026-05-05T10:30:00Z"       # 创建时间
last_reviewed_by = "human_editor_A"       # 最后审核者
last_reviewed_at = "2026-05-06T14:00:00Z" # 最后审核时间
based_on_chapters = ["ch001-ch010"]       # 基于哪些章节数据归纳的
confidence = 0.85                          # AI推断的置信度
version = 3                                # 版本号（随更新递增）
staleness_threshold = 10                   # 超过N话未审核则标记过期

[speech_patterns]
self_reference = ["僕"]
honorific_others = "一律加さん，对师傅用先生"
honorific_received = "同龄人直呼名字，长辈叫「灯くん」"

[relationship_speech]
# 角色对不同对象的语言行为——同一角色的语言随对象变化
# 这是"关系图谱的语言切面"，描述角色在不同社会关系中的语言表现
[relationship_speech."对师傅·的場"]
honorific_level = "尊敬語"               # 敬语层级
self_ref = "僕"                          # 对此人时的自称（可能与默认不同）
sentence_style = "句末多用です/ます，从不省略主语"  # 句式特征
emotional_override = "即使师傅说了过分的话也维持敬语"  # 情绪对敬语的覆盖规则

[relationship_speech."对同门·氷室"]
honorific_level = "タメ語（但偶尔滑回敬语）"
self_ref = "俺"                          # 对熟人时切回俺
sentence_style = "短句，会顶嘴，但语气软"
emotional_override = "紧张时会不自觉变回敬语，暴露内心距离感"

[relationship_speech."对店主·小日向"]
honorific_level = "丁寧語"
self_ref = "僕"
sentence_style = "礼貌但简短，不太主动说话"
emotional_override = "稳定，不随情绪变化"

[catchphrases]
patterns = ["…んですよね", "あ、はい"]
notes = "句末喜欢加「んですよね」确认语气，紧张时「あ、はい」反复出现"

[tone_spectrum]
working = "自言自语多，专业术语密集，句子碎片化"
casual = "话少但不冷，偶尔冒出冷笑话"
combat = "反常地冷静，句子变长变完整，像是换了个人"
emotional = "憋到最后才爆发，爆发时敬语全部消失"

[[voice_evolution]]
chapter = 8
trigger = "师傅的场被发现私售劣质硝子"
change = "对师傅的称呼从「先生」降级为「的場さん」"
reason = "信任崩塌但不愿撕破脸，用称呼降级表达距离"

[[voice_evolution]]
chapter = 23
trigger = "冰室受伤事件"
change = "对冰室首次使用「お前」，之后再没改回去"
reason = "生死关头突破了社交距离的心理防线"

[translation_notes]
zh_equivalents = { "僕" = "我（保持温和感，不译'老子'）", "んですよね" = "……对吧", "先生" = "老师" }
avoid = "不要翻译得太文艺，灯不是诗人，只是话少"
prefer = "口语感，但保留一点笨拙感——他不是不善言辞，是选择少说"
```

### 5.3 角色关系图谱

```
Graph = {
  nodes: {
    "amamiya_akari": { name: "雨宫灯", type: "protagonist", profile_ref: "amamiya_akari.toml" },
    "nohtarou": { name: "的場 弦之介", type: "master", profile_ref: "nohtarou.toml" },
    "himuro": { name: "冰室 零", type: "rival_ally", profile_ref: "himuro.toml" },
    "kohinata": { name: "小日向 葵", type: "support", profile_ref: "kohinata.toml" }
  },
  edges: {
    ("amamiya_akari", "nohtarou"): {
      relation_type: "师徒→幻灭",
      power_dynamic: "师傅主导（前期），灯沉默反抗（后期）",
      speech_pattern: {
        "akari→nohtarou": { honorific: "先生→さん（ch8降级）", tone: "尊敬→克制的失望" },
        "nohtarou→akari": { honorific: "灯くん", tone: "居高临下的慈爱（前期），无视（后期）" }
      },
      evolution: [
        { chapter: 1, type: "师徒" },
        { chapter: 8, type: "幻灭但未决裂" },
        { chapter: 31, type: "正面对决" }
      ]
    },
    ("amamiya_akari", "himuro"): {
      relation_type: "同门→对手→伙伴",
      power_dynamic: "对等",
      speech_pattern: {
        "akari→himuro": { honorific: "タメ語（偶尔滑回敬语）", tone: "嘴硬心软" },
        "himuro→akari": { honorific: "名字直呼", tone: "挑逗+保护欲" }
      },
      evolution: [
        { chapter: 1, type: "互看不顺眼" },
        { chapter: 15, type: "默契搭档" },
        { chapter: 23, type: "生死与共" }
      ]
    }
  }
}
```

### 5.4 翻译实例：同一场景下的多角色语言差异

以下用三个场景展示角色档案如何驱动翻译决策。所有对白均为虚构作品「硝子と刃」。

#### 场景一：ch003 — 日常工坊（关系基线）

的場在工坊指点灯和冰室，小日向来送材料。此时师徒关系完好。

```
的場：灯くん、その硝子の温度、まだ足りてないぞ。
灯 ：あ、はい。申し訳ありません、先生。もう少し見てみます。
氷室：（嘟囔）毎回同じこと言うんだよな……
灯 ：（小声）氷室、先生の前で……
氷室：（小声）だって事実だろ。
小日向：ご注文の材料をお届けしました。確認お願いします。
灯 ：あ、ありがとうございます。小日向さん、いつも助かります。
```

翻译要点——

| 对白 | 翻译策略 | 理由 |
|------|---------|------|
| 的場叫灯「灯くん」 | "灯"（不加后缀） | 中文不译くん，用名字直称传递亲近+上下级 |
| 灯回「先生」 | "老师" | 固定译法，维持尊敬 |
| 灯的「あ、はい」 | "啊，好的" | 口癖保留，体现灯的紧张习惯 |
| 灯叫「小日向さん」 | "小日向小姐" | 对外人加称谓后缀，与对师傅的「先生」区分 |
| 冰室的「毎回同じこと」 | "又是老一套" | タメ語→口语化，不加敬语 |
| 灯对冰室小声说话 | "冰室，老师面前……" | 灯对冰室偶尔滑回礼貌用语，译文用"面前"而非"跟前儿"保持中性 |

**关键：灯在同一场景中对三个人说三种话。**
- 对的場：尊敬語 + 自称「僕」 + 口癖活跃（あ、はい）
- 对冰室：タメ語 + 自称切换「俺」 + 短句顶嘴
- 对小日向：丁寧語 + 自称「僕」 + 话少

翻译如果统一用同一种腔调，角色就扁了。

#### 场景二：ch009 — 降级之后（称呼变化+溢出效应）

的場私售劣质硝子被发现后，灯首次用「的場さん」称呼师傅。同场景有冰室和小日向。

```
的場：灯くん、今日の仕上がり見せろ。
灯 ：……的場さん、先にあの件のことを話しませんか。
的場：（微皱眉）……随你。
氷室：（惊）え、今の……？
灯 ：（对冰室摇头，小声）あとで。
小日向：那个……两位还好吗？
灯 ：没事。小日向さん、材料放在那里就好。
```

翻译要点——

| 对白 | 变化 | 理由 |
|------|------|------|
| 灯不再叫「先生」，改「的場さん」 | 称呼降级 | 信任崩塌的信号。中文译"的場先生"保留姓氏距离感 |
| 的場仍叫「灯くん」 | 未变 | 上位者不因下位者的态度改变称呼——权力不对等 |
| 冰室「え、今の……？」 | 旁观者注意到语言变化 | 译"等等，你刚才……？" ——冰室震惊于灯打破了敬语规则 |
| 灯对小日向「没事」 | 未变 | 对外人的丁寧語不受师徒关系变化影响 |
| 灯对冰室「あとで」 | 未变 | 对同门的タメ語不受影响，但主动中断对话暗示内心波动 |

**溢出效应**：灯对的場的称呼降级**没有**蔓延到对小日向和其他长辈。但如果ch15出现新师傅角色，灯可能本能地犹豫——档案需要标记这个风险（confidence降低，注明"可能对新权威人物产生不信任"）。

#### 场景三：ch023 — 冰室受伤（情绪突破+敬语崩塌）

硝子工坊爆炸，冰室被碎硝子刺伤。灯冲进来。

```
灯 ：氷室——！！誰か、誰か呼んでくれ！！
氷室：（虚弱）うるさい……俺は大丈夫だって……
灯 ：大丈夫じゃねえだろうが！！血が——
（灯转向门口的的場）
灯 ：的場……お前、知ってたのか。この硝子が危険だってこと。
的場：（沉默）
灯 ：答えろ！！
```

翻译要点——

| 对白 | 变化 | 理由 |
|------|------|------|
| 灯大喊「誰か呼んでくれ」 | 敬语全消失 | 生死关头，句子从礼貌体直接跳到命令式。译"来人啊！叫人来！！"——感叹号密集，短句 |
| 灯对冰室「大丈夫じゃねえだろうが」 | 首次用粗口+「じゃねえ」 | 之前灯对冰室最多是タメ語，现在连タメ语都破了。译"好个屁啊！！"——比正常灯的语气粗暴三倍 |
| 灯对的場首次用「お前」 | 从「先生→さん」再降级到「お前」 | 最终决裂。译"你"（不用"您"），且直呼其姓不加任何称谓 |
| 灯叫「答えろ」 | 命令形 | 学生对师傅用命令形是关系破裂的终级信号。译"回答我！！"——短句+感叹号 |
| 冰室「うるさい……」 | 即使受伤也维持タメ語 | 冰室的性格不受情绪影响——他本来就不太礼貌。译"吵死了……"——保持一贯语气 |

**这张表展示了情绪如何逐层击穿语言防线：**

```
正常状态：  僕 + 先生 + です/ます
紧张状态：  僕 + 的場さん + です/ます（称呼降级，但敬语维持）
愤怒爆发：  俺 + お前 + 命令形（所有防线同时崩溃）
```

崩塌顺序：自称（僕→俺）→ 称呼（先生→さん→お前）→ 句式（です/ます→命令形）。翻译需要**同步**这三个维度的降级，不能只换称呼不改语气。

#### 场景四：ch28 — 溢出效应（新权威人物）

灯遇到另一位工匠前辈·白石。按照灯的习惯，对前辈应该用尊敬語。但经历了的場的背叛后：

```
白石：雨宮くん、うちの工坊で見学しないか？
灯 ：あ……はい。白石……さん。よろしくお願いします。
（内心OS：「さん」をつけるの、なんだか重くなった。）
```

翻译要点——

| 对白 | 问题 | 理由 |
|------|------|------|
| 灯叫「白石さん」 | 犹豫 | 正常应该直接说，但灯卡了一下。译"白石……先生。请多指教。"——省略号传递犹豫 |
| 内心OS | 自我觉察 | 译"加'先生'这件事……突然变得好重。"——灯意识到自己对敬语产生了PTSD |

**溢出效应不是自动改变，是犹豫。** 灯没有直接对白石不礼貌，但语言中的停顿暴露了心理变化。翻译不能简单地降级敬语，而是要通过节奏（省略号、短暂停顿）传递"这个人想维持礼貌但内心在抗拒"的状态。

---

## 6. 全局提示词设计

### 6.1 Vision Stage

```
你是一位资深漫画编辑兼视觉叙事分析师。

必须：识别所有分镜格、对话气泡、旁白框；提取原文；判断说话人、
气泡类型、情绪状态；识别拟声词及其视觉角色；识别虚构文字；
输出叙事摘要和情绪基调。

必须先以“整页视觉理解”为主，再回到气泡级提取：
- 先读整页构图、角色站位、镜头关系、动作变化、视觉焦点
- 再把每个气泡放回对应分镜和画面语境中解释
- 如果气泡文字本身不足以判断语义，必须依赖画面而不是只读文本
- 不得把 Vision Stage 退化成“气泡 OCR + 文本转写”

不能：编造不存在的文字；猜测模糊文字（标 text_unclear）；
将拟声词误认为对话。

输出：严格遵循 Page JSON schema。
```

### 6.2 Translation Stage

```
你是一位专业漫画翻译，精通日语→中文。

原则：忠实优先但可本地化；角色语言一致性；情绪匹配；
长度适配气泡大小；文化适配（敬语、拟声词、双关语）。

你会收到：原文、说话人档案、画面描述、角色前几页翻译样本、前后文。

不能：编造对话、添加解释文字、无依据改变语言风格。

每条输出：翻译文本 + 翻译理由 + 置信度 + 是否需人工审查。
```

### 6.3 QA Stage

```
你是一位漫画翻译校对专家。

校对维度（按优先级）：
1. 事实准确性 — 翻译内容是否与原文一致
2. 角色一致性 — 语言风格是否符合角色档案
3. 对话层级 — 称呼、敬语、句式是否符合角色间社会关系设定
   （学生对老师即使愤怒也用敬语——层级错了等于人设崩了，需要重写整句）
4. 情绪一致性 — 情绪传递是否准确
   （情绪偏差只需换词，优先级低于需要重写句子的对话层级错误）
5. 语言演化 — 角色语言是否随剧情合理变化
6. 文风润色 — 表达是否自然流畅

不能：自己重新翻译、编造信息、无依据修改角色语言。

每条建议：bubble_id + 原翻译 + 建议修改 + 修改类型 + 理由 + 置信度。
置信度 < 0.7 → 标记"需人工审查"。
```

QA Stage 不只是事实纠错器，而是人格一致性的审查层。它除了检查漏译、误译和 hallucination，还要检查：

- 人设崩坏：角色突然说出明显不像自己会说的话
- 关系层级错位：对不同对象的称呼、敬语、距离感不成立
- 语气漂移：同一角色在连续页面中的说话质感不稳定
- 情绪轨迹断裂：语言强度与剧情阶段不匹配
- 视觉语境丢失：译文只对上了气泡字面意思，却没有吸收画面里的动作、站位、视线、镜头切换

---

## 7. RAG / Wiki 记忆架构

### 7.1 存储

```
project_root/
├── memory/
│   ├── state/
│   │   ├── characters/
│   │   ├── scenes/
│   │   ├── terms/
│   │   ├── decisions/
│   │   └── index.json
│   ├── characters/
│   ├── scenes/
│   ├── terms/
│   ├── decisions/
│   └── indexes/
├── character_profiles/        # 角色档案（结构化历史资产）
├── character_graph.json       # 角色关系图谱
├── terminology/               # 作品术语库（见 §8）
├── fictional_scripts/         # 虚构文字数据库
├── translations/              # 翻译历史
├── voice_changelog.toml       # 语言演化日志
└── project_meta.toml          # 项目元数据
```

这些资产不是附属资料，而是人格一致性系统的长期记忆与生成约束。这里采用双层结构：

- `memory/state/`：runtime canonical source
- `memory/characters/`、`memory/scenes/`、`memory/terms/`、`memory/decisions/`、`memory/indexes/`：human-readable projection + annotation layer

repo `docs/` 中的 `characters/`、`scenes/`、`terms/`、`decisions/`、`indexes/` 只保留模板和示例，不作为真实运行时知识库存储目录。

### 7.1.1 结构化实体

最小 memory state 定义：

- `CharacterState`
- `SceneState`
- `TermState`
- `DecisionState`
- `MemoryIndex`

这些实体服务于跨页、跨话、跨运行的长期记忆，与 `Page` / `Bubble` / `Utterance` / `TranslationCandidate` 这类单次流水线对象分层。

### 7.2 检索流程

```
翻译每个气泡时：
1. memory/state/index.json → 先做结构化索引定位
2. memory/state/characters/ → 读角色结构化状态
3. memory/state/scenes/ → 读最近相关场景状态
4. character_graph.json → 查说话人关系边与敬语切换规则
5. character_profiles/ → 读角色历史档案（兼容旧资产）
6. translations/ → 检索该角色最近 5 页翻译
7. voice_changelog.toml → 最近语言变化
8. memory/state/terms/ + terminology/ → 查术语状态和结构化术语库
9. 如需解释与人工可读上下文，再引用对应 wiki projection
```

这里的检索目标不只是“补充上下文”，更是恢复“谁在对谁说，以及应该怎么说”。
第一版 retrieval 的优先级为：

1. 结构化过滤与索引查找
2. wiki 关键词检索
3. 向量检索（后续增强）

### 7.3 更新流程

```
每页翻译完成后：
1. 翻译结果写入 translations/chXXX/pXXX.json
2. 更新对应 memory/state 实体
3. 从结构化 state 自动投影生成或更新 wiki 页
4. QA 检测到语言变化 → 更新 voice_changelog.toml
5. 检测到新关系模式 → 更新 character_graph.json
6. 检测到新术语 → 更新 TermState 与 terminology/（标记 pending_human_review）
7. 若形成可复用规则，再更新对应 index
8. 角色档案与高影响决策仍可要求人工确认
```

`--learn-from` 学习的不只是词汇映射，更是角色在中文中的人格质感与关系约束表达。

### 7.4 Wiki 页生成与回写规则

`memory/` 下的 wiki 页是本项目的“可读记忆层”。它的职责不是替代结构化存储，而是把结构化判断写成能够被人直接审阅、修订和回滚的笔记。

#### 7.4.1 生成规则

1. **结构化层先行**：所有 runtime 可消费信息先进入 `memory/state/`。
2. **场景页承载局部事实**：每个关键场景都应记录在 `memory/scenes/`，包括情绪转折、关系变化、关键对白、对后续章节的影响。
3. **术语页记录选择，不只记录结果**：`memory/terms/` 必须写明候选译法、采用理由、弃用理由和适用边界。
4. **决策页记录高成本判断**：凡是会影响后续多话的一致性决策，必须进入 `memory/decisions/`，保留可回滚依据。
5. **索引页负责路由**：`memory/indexes/` 只维护入口、主题聚类和跨页链接，不写长正文。

#### 7.4.2 回写规则

1. **structured -> wiki 自动投影**：结构化 state 更新后自动生成或更新 Markdown 页。
2. **wiki -> structured 显式同步**：人工对 wiki 的修改必须通过显式 sync/compile 步骤回写结构化层。
3. **双写不同步时，以 structured 为 runtime 依据，以 wiki 为审阅入口**。
3. **一条判断只允许一个主出处**：避免同一决策散落多处导致后续维护失真。wiki 页可链接，不能无主地重复叙述。
4. **更新必须带溯源**：每次改写 wiki 页时，要写清章节、页码、bubble_id、触发原因。
5. **过期信息必须显式标记**：旧结论不要静默删除，改为标记 deprecated / superseded，并链接新版本。

未同步的 wiki 改动不得直接进入 runtime。

#### 7.4.3 命名规范

- 角色页：`memory/characters/{work}/{character-slug}.md`
- 场景页：`memory/scenes/{work}/ch{chapter}-p{page}-{scene-slug}.md`
- 术语页：`memory/terms/{work}/{term-slug}.md`
- 决策页：`memory/decisions/{work}/ch{chapter}-{decision-slug}.md`
- 索引页：`memory/indexes/{work}.md`
- 状态文件：`memory/state/{entity_type}/{work}/{slug}.json`

命名要稳定、短、可链接。slug 优先使用小写字母、数字和连字符；中文标题保留在文件内正文。

---

## 8. 文化适配层

### 8.1 问题分类

| 类型 | 日语示例 | 翻译挑战 |
|------|---------|---------|
| **作者造词** | 硝子継ぎ / 純晶 / 血硝子 | 每部作品一套术语系统，需统一译名 |
| **文化独有概念** | 木漏れ日 / 物の哀れ / 侘寂 | 中文无等价物，直译丢意境 |
| **社会关系词汇** | 先輩 / 後輩 / お世話になってる | 有近似但文化负载不同 |
| **日常文化表达** | いただきます / お疲れ様 / しょうがない | 字面意思 ≠ 文化含义 |
| **敬语系统** | です/ます vs だ/である vs 俺/僕/私 | 中文无语法化敬语，需词汇补偿 |
| **拟声词文化编码** | シーン（寂静）/ ドキッ（心跳） | 日文拟声词是画面的一部分 |

### 8.2 翻译策略

| 策略 | 含义 | 适用场景 | 示例 |
|------|------|---------|------|
| **literal** | 直译 | 造词有明确结构 | 硝子継ぎ → 硝子接合 |
| **adapt** | 本地化 | 社会关系词 | 先輩 → 前辈 |
| **coined** | 创造新译词 | 无对应概念 | 木漏れ日 → 「叶隙光影」 |
| **transliterate** | 音译 | 专有名词 | おにぎり → 饭团（日式） |
| **contextual** | 上下文选择 | 多义文化词 | しょうがない → 没办法/认了 |
| **preserve** | 保留原文 | 美学概念 | 木漏れ日 → 木漏れ日 |
| **hybrid** | 译词+注释 | 首次出现的核心概念 | 侘寂 → 侘寂（以不完美为美） |

### 8.3 术语数据库

```toml
# terminology/glass_and_blade.toml

[system]  # 世界观术语（造词）
硝子継ぎ = { zh = "硝子接合", type = "ability", strategy = "literal", notes = "灯的独有技艺，将碎裂的硝子重新熔接" }
純晶 = { zh = "纯晶", type = "material", strategy = "coined", notes = "无瑕的原始硝子原料" }
血硝子 = { zh = "血硝子", type = "material", strategy = "literal", notes = "注入使用者血液的诅咒硝子，有副作用" }
硝子衆 = { zh = "硝子众", type = "institution", strategy = "adapt", notes = "硝子工匠的行会组织" }

[culture]  # 文化负载词汇
先生 = { zh = "老师", strategy = "adapt", notes = "灯对的場的称呼（降级前）" }
お疲れ様です = { zh = "辛苦了", strategy = "contextual", notes = "工坊收工时的问候语" }

[aesthetic]  # 美学概念
硝子色 = { zh = "硝子色", strategy = "preserve", notes = "特定光照下硝子的色彩变幻，无中文等价物" }

[untranslatable]  # 不翻译
# 暂无
```

### 8.4 作者造词自动发现

Vision Stage 增加 `coined_terms` 和 `cultural_terms` 输出字段。

自动发现逻辑：
- **反复出现的复合名词** → 可能是造词（频率检测）
- **片假名标注的日常概念** → 可能是外来概念或特殊用法
- **带ルビ（注音）的汉字** → 作者在强调读法，通常是造词
- **首次出现后直接使用不解释** → 是世界观术语

新发现的术语写入 `terminology/`，标记 `pending_human_review: true`。

### 8.5 敬语补偿策略

日文敬语不只是"客气"——它表达社会关系层级、亲疏、场合正式度、当下情绪。中文无语法化敬语，需多维补偿。

```
维度一：词汇补偿（原有）
丁寧語（です/ます）    → 正常语序，不太口语化
尊敬語（お〜になる）    → 加「请」「麻烦」「劳烦」
謙譲語（お〜する）     → 加「我来」「让我」
タメ語（だ/である）    → 口语化：「啊」「嘛」「呗」
乱暴語（くらえ/てめえ）→ 粗口+感叹号+短句

维度二：句式补偿（新增）
尊敬 → 更长、更完整的句子结构（「能否请您……」vs「来一下」）
谦逊 → 主动降格句式（「我来做就好」vs「交给我」）
亲密 → 短句、省略句、语气词（「走呗」vs「我们走吧」）

维度三：标点与节奏补偿（新增）
尊敬 → 标点规整，少用感叹号和省略号
亲密 → 多用感叹号、省略号、破折号表达情绪
紧张/敌意 → 短句+感叹号密集，省略号表威胁停顿

维度四：体态语标注（新增，漫画特有）
漫画对话中常伴随体态描述（鞠躬、低头、侧目），翻译时需在
旁白/描述中保留这些信息以传递敬语的社会含义：
- 深鞠躬 → 强化尊敬语气
- 侧目/撇嘴 → 弱化或反讽敬语
- 背对说话 → 可能表示拒绝使用对方期望的敬语层级

称呼体系：
名前+さん → 名字（中文日常称呼不加后缀）
名字+さん → 姓氏+先生/女士（正式）
あだ名    → 昵称（直接翻译昵称含义）

关键规则：敬语层级由角色间社会关系设定决定，不由瞬时情绪决定。
学生对老师始终用敬语，哪怕愤怒——这是角色设定，不是情绪表达。
```

### 8.6 翻译学习引擎（Translation Learning Engine）

热启动的核心组件。给定一组原图+已翻译图的配对，自动提取翻译模式。

#### 8.6.1 输入

```
学习输入：
├── originals/          # 原始漫画图片
│   ├── ch01_p001.png
│   └── ...
└── translated/         # 已翻译的对应图片（同文件名或同页码）
    ├── ch01_p001.png
    └── ...
```

支持的已有翻译来源：
- 粉丝汉化组作品（最常见的场景）
- 官方中文版
- 其他语言翻译（日→英，然后学习英→中的模式）
- 用户自译稿

#### 8.6.2 学习流程

```
┌─────────────────────────────────────────────────────────┐
│            Stage L1: 双页对齐（Alignment）                 │
│                                                          │
│  输入：原图目录 + 翻译图目录                                │
│  处理：                                                   │
│    - 文件名匹配（ch01_p001.png ↔ ch01_p001.png）          │
│    - 视觉相似度验证（确保是同一页的不同版本）                 │
│    - 页码提取（从文件名/元数据/页码水印）                    │
│  输出：配对列表 [(original, translated, page_id), ...]     │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│         Stage L2: 双页视觉理解（Dual Vision）               │
│                                                          │
│  输入：一对 (原图, 翻译图)                                  │
│  模型：多模态 LLM                                         │
│  处理：                                                   │
│    - 原图：提取日文原文 + 气泡位置 + 角色信息                │
│    - 翻译图：提取中文译文 + 气泡位置                         │
│    - 对齐：将原文气泡与译文气泡一一配对                       │
│  输出：Aligned Page JSON                                  │
│                                                          │
│  Aligned Page JSON = {                                    │
│    page_id,                                              │
│    pairs: [{                                              │
│      bubble_id,                                          │
│      original_jp: "硝子子継ぎ——繋ぎ直し！！",                  │
│      translated_zh: "硝子接合——重新接合！！",                │
│      speaker_hint: "粉色头发少年",                         │
│      bubble_type: "shout",                               │
│      translation_strategy_used: "literal"                 │
│    }, ...]                                               │
│  }                                                        │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│       Stage L3: 模式提取（Pattern Extraction）              │
│                                                          │
│  输入：所有 Aligned Page JSON                              │
│  模型：LLM（批量分析）                                     │
│  提取维度：                                               │
│                                                          │
│  A. 角色语言模式                                          │
│    - 每个角色的自称（俺→我 / 僕→我 / 私→我）              │
│    - 称呼方式（先生→老师 / ちゃん→）                       │
│    - 口癖映射（だぜ→呗 / ッス→啊）                         │
│    - 语气特征（长句/短句/感叹号频率/省略号频率）            │
│                                                          │
│  B. 术语表                                                │
│    - 反复出现的日文词 → 固定译名                           │
│    - 世界观术语的统一翻译                                   │
│    - 拟声词的翻译习惯                                      │
│                                                          │
│  C. 文化适配策略                                          │
│    - 敬语如何处理（直译/省略/词汇补偿）                     │
│    - 文化独有概念如何处理（保留/造词/注释）                 │
│    - 日语特有表达的本地化方式                               │
│                                                          │
│  D. 翻译风格指南                                          │
│    - 整体风格（直译/意译/归化/异化）                        │
│    - 语气偏好（书面/口语/文言混用）                         │
│    - 长度控制（精简/扩展/忠实原文长度）                     │
│    - 标点习惯（全角/半角/感叹号频率）                       │
│                                                          │
│  E. 角色关系模式                                          │
│    - 谁对谁用敬语                                         │
│    - 谁对谁用昵称                                         │
│    - 关系如何随剧情变化                                     │
│                                                          │
│  输出：                                                   │
│    - character_profiles/ (TOML)                           │
│    - terminology/{work}.toml                              │
│    - style_guide.toml                                     │
│    - character_graph.json                                 │
└──────────────────────────┬──────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│       Stage L4: 验证与补全（Validation）                    │
│                                                          │
│  输入：学习生成的档案                                       │
│  处理：                                                   │
│    - 一致性检查：同一角色在不同章节的语言模式是否一致         │
│    - 完整性检查：是否所有出现的角色都有档案                   │
│    - 演化检查：语言变化是否被捕获                            │
│    - 术语覆盖率：反复出现的词是否都在术语表中                 │
│  输出：                                                   │
│    - 最终档案（标记 confidence）                            │
│    - 缺失项列表（需要人工补充的）                            │
│    - 学习质量报告                                          │
└──────────────────────────┬──────────────────────────────┘
```

#### 8.6.3 学习提示词

```
你是一位漫画翻译分析师。你会收到一对漫画页面——原图（日文）和已翻译的版本（中文）。

你的任务是提取翻译模式，不是翻译新内容。

你需要分析：
1. 角色语言模式：
   - 每个角色的日文自称被翻译成了什么中文？
   - 角色之间的称呼方式是什么？
   - 角色有口癖吗？口癖被翻译成了什么？
   - 角色的语气特征是什么（长句/短句/粗暴/温柔）？

2. 术语提取：
   - 哪些日文词被统一翻译成同一个中文词？（这是术语）
   - 哪些日文词被保留没翻译？（这是选择保留的）
   - 有哪些拟声词？它们怎么翻译的？

3. 翻译风格：
   - 整体风格是直译还是意译？
   - 敬语怎么处理的？
   - 文化独有概念怎么处理的？

4. 角色关系：
   - 谁对谁用敬语？
   - 称呼方式暗示什么关系？

你不能：
- 自己翻译内容（你只分析已有翻译）
- 假设没有证据的翻译模式
- 忽略不一致的地方（标注出来）

输出：结构化 JSON，包含角色档案、术语表、风格指南、关系图谱。
```

#### 8.6.4 热启动 vs 冷启动的对比

```
                    热启动                    冷启动
                 （有已有翻译）              （无已有翻译）
                    
角色档案      学习引擎自动生成            Vision 自动发现
              质量高（基于实际翻译）        质量中（基于推理）
              
术语库        从翻译对中提取              从 Vision 中识别
              完整度高                    需要多话积累
              
翻译风格      从已有翻译中总结            使用默认风格
              与已有翻译一致              用户可配置
              
角色关系      从称呼体系推断              从对话推断
              数据量大时准确              早期可能不准
              
冷启动时间    学习阶段需要时间             立即开始翻译
              但后续翻译更快              逐步建立档案
              
最佳场景      粉丝汉化组想继续翻译         全新作品首次翻译
              官方版后续章节              无任何翻译参考
```

#### 8.6.5 增量学习

热启动不是一次性的。翻译过程中持续学习：

```
每翻译完成一话：
1. 将翻译结果视为"新的翻译对"（原图 + 译图）
2. 与学习阶段的模式对比
3. 如果发现新模式 → 更新档案
4. 如果发现矛盾 → 标注，不自动覆盖

用户手动修改翻译后：
1. 修改被视为"用户偏好信号"
2. 同类模式的翻译自动调整
3. 角色档案根据修改更新（需要累积3次以上同类修改才写入）
```

### 8.7 文化适配在 Pipeline 中的位置

```
Stage 1 (Vision) → 识别 coined_terms / cultural_terms
Stage 2 (角色归属) → 检索 terminology DB，匹配文化词汇策略
Stage 3 (翻译) → 按策略处理每个文化词汇，输出时标注策略类型
Stage 4 (QA) → 检查文化词汇处理是否一致、是否符合策略
Stage 5 (嵌字) → 保留/注释的文化词在嵌字时特殊排版
```

---

## 9. 虚构文字处理

### 9.1 分类

| 类型 | 定义 | 示例 | 处理 |
|------|------|------|------|
| standard | 标准文字系统 | 日文/英文 | 正常翻译 |
| fictional_known | 有对照表 | 深渊文字 | 查表翻译 |
| fictional_partial | 部分虚构 | 咒术回战咒语 | 识别标准部分 |
| untranslatable | 不可翻译 | 电锯人背景文字 | 保留原图 |
| decorative | 装饰性 | 背景涂鸦 | 保留原图 |

### 9.2 数据库

```toml
# fictional_scripts/abyss_script.toml
[meta]
name = "深渊文字"
source = "来自深渊"
has_mapping = true

[mapping]
"ア" = "a"
"イ" = "i"

[notes]
某些字符有双重含义，需要上下文判断
```

---

## 10. 嵌字规范

### 10.1 字体映射

| 气泡类型 | 字体 | 大小 | 样式 |
|---------|------|------|------|
| normal | 思源黑体 Regular | 自适应 | 正常 |
| shout | 思源黑体 Heavy | 1.5x | 描边加粗 |
| whisper | 思源黑体 Light | 0.8x | 细线 |
| thought | 思源宋体 Regular | 正常 | 斜体 |
| narration | 思源宋体 Medium | 正常 | 正常 |
| sfx_impact | 手写体/毛笔体 | 2x+ | 倾斜/描边 |
| sfx_ambient | 细宋体 | 缩小 | 半透明 |

### 10.2 排版规则

- 日漫气泡：竖排优先，居中
- 条漫气泡：横排，左对齐
- 旁白框：横排，两端对齐
- 文字不溢出气泡
- 行间距：1.2-1.5x
- padding：≥ 15% 气泡宽度

---

## 11. 错误处理

| 失败场景 | 降级策略 |
|---------|---------|
| Vision API 超时 | 重试 2 次 → OCR fallback |
| 角色无法识别 | 标注 unknown_speaker |
| 翻译 confidence < 0.5 | 保留原文，标需人工翻译 |
| 擦除效果差 | 原图叠加标记 |
| 虚构文字无对照表 | 保留原图 |
| 格式解析失败 | 跳过文件，继续后续 |
| 主供应商不可用 | 自动 fallback 到备选/本地 |
| 本地模型不可用 | 尝试云端 → 拒绝处理 |

---

## 12. 实现路线图

### Phase 1: CLI MVP（核心 pipeline）

- [ ] external runtime core 宿主接入
- [ ] artifact / report / review 归一化
- [ ] `manga-translate input/ -o output/` 默认 external-core
- [ ] legacy internal pipeline 迁入 research 命名空间
- [ ] 建立可审查的运行产物合同，为后续角色一致性系统打底

### Phase 2: 格式扩展

- [ ] PDF 输入/输出（PyMuPDF）
- [ ] EPUB 输入/输出（ebooklib）
- [ ] CBR/CBZ 输入/输出
- [ ] MOBI 输入（依赖 Calibre）
- [ ] 双语对照 PDF 输出
- [ ] 翻译报告 JSON 输出

### Phase 3: 翻译学习引擎

- [ ] `--learn-from` 参数：输入原图+翻译图配对目录
- [ ] Stage L1：双页对齐（文件名匹配+视觉验证）
- [ ] Stage L2：双页视觉理解（原图+翻译图对提取）
- [ ] Stage L3：模式提取（角色语言/术语/风格/关系）
- [ ] Stage L4：验证与补全（一致性/完整性检查）
- [ ] 自动生成：character_profiles/ + terminology/ + style_guide.toml + character_graph.json
- [ ] `--learn-only` 模式：只学习不翻译
- [ ] 增量学习：翻译过程中持续更新档案
- [ ] 将 `--learn-from` 明确定义为人格校准入口，而不只是术语热启动

### Phase 4: 角色系统

- [ ] 角色档案 RAG（TOML 创建/加载/热启动自动填充）
- [ ] 角色归属（自动识别说话人）
- [ ] 角色一致性翻译（注入档案）
- [ ] QA Stage（事实 + 角色一致性）
- [ ] 正式进入“角色一致性对白生成”能力，而不再只是上下文增强翻译

### Phase 5: 文化适配

- [ ] 术语数据库（per-work TOML）
- [ ] 作者造词自动发现
- [ ] 文化词汇分级策略
- [ ] 敬语补偿系统
- [ ] QA 文化层检查

### Phase 6: 关系图谱 + 高级 QA

- [ ] NetworkX 角色图谱
- [ ] 关系驱动翻译（敬语匹配）
- [ ] 关系演化检测
- [ ] 情绪一致性 + 语言演化 QA
- [ ] 作为人格一致性的强化与审计层，支撑跨章节稳定性

### Phase 7: UI

- [ ] CLI → Web UI（FastAPI + React）
- [ ] 项目管理界面（创建/管理翻译项目）
- [ ] 角色档案可视化编辑器
- [ ] 翻译对照查看器（原文/译文/嵌字成品并排）
- [ ] QA 审查界面（逐条接受/拒绝修改建议）
- [ ] 术语库管理界面
- [ ] 供应商配置界面

### Phase 8: 高级特性

- [ ] 增量翻译（新话加载前文档案）
- [ ] 批量处理 + 进度管理
- [ ] 多作品/长篇连载支持
- [ ] 翻译记忆库（跨作品复用）
- [ ] 插件系统（自定义翻译引擎、嵌字渲染器）
- [ ] MCP Server（供其他 agent 调用）

---

## 13. 技术选型

| 组件 | 首选 | 备选 | 说明 |
|------|------|------|------|
| 多模态 Vision | GPT-4o | Gemini 2.5 Pro / Ollama+Qwen2-VL | 按需切换 |
| 翻译 LLM | GPT-4o-mini | DeepSeek V3 / Ollama+Qwen2 | 成本优先 |
| QA LLM | GPT-4o | Claude Sonnet / LM Studio | 推理能力 |
| 擦除模型 | LaMa Large | MAT | 开源 |
| 嵌字引擎 | PIL + HarfBuzz | Pillow | 文字渲染 |
| RAG 存储 | 本地文件（TOML+JSON） | ChromaDB | Phase 1 简单 |
| 图模型 | NetworkX | Neo4j | Phase 1 NX |
| CLI 框架 | Click | Typer | Python CLI |
| Web UI | FastAPI + React | — | Phase 6 |
| 配置管理 | TOML | — | 人类可读 |
| PDF 处理 | PyMuPDF | Poppler | 逐页渲染 |
| EPUB 处理 | ebooklib | zipfile | OPF 解析 |
| MOBI 转换 | Calibre | kindleunpack | 外部依赖 |
| CBR/CBZ | zipfile + rarfile | patoolib | RAR 需 unrar |

补充质量目标：

- 角色一致性：同一角色跨页、跨章的语言风格是否稳定
- 关系语气稳定性：面对不同对象时的称呼、敬语、距离感是否一致
- 人设偏移识别有效性：QA 是否能识别明显的语气漂移与关系失真

---

## 14. 开放问题

1. **成本控制**：长篇连载（500话）= $300+（GPT-4o）。增量更新 + 缓存策略？
2. **角色冷启动**：新作品无预建档案，第一话自动推断？
3. **并发更新**：多 agent 处理不同章节，档案并发写入？
4. **质量评估**：人工标注 + BLEU + LLM-as-Judge？
5. **版权合规**：工具声明仅用于合法用途？
6. **竖排排版**：PIL 中文竖排支持差，引入 libass？
7. **EPUB 漫画 vs 文字书**：自动检测？
8. **MOBI 未来**：Amazon 弃用中，是否值得支持？
9. **PDF 类型检测**：扫描件 vs 数字 PDF 自动区分？
10. **本地模型质量**：小模型（7B）做 Vision 和翻译，质量差距多大？需要 benchmark。
11. **目标用户定位**（来自日语专家反馈）：普通读者对"角色语气一致性"敏感度远低于预期，他们更关心"快、免费、能看懂"。真正的价值用户是翻译者/字幕组等"辅助翻译工具"使用者。需明确：面向终端读者 vs 面向翻译工作者，产品设计完全不同。
12. **档案维护成本**（来自日语专家反馈）：如果人工录入+维护角色档案的时间超过翻译本身，系统会退化成普通机翻。需确保：AI自动生成的档案准确率足够高，人工只做审核不做填写；档案有staleness机制，过期自动提示更新而非让人类逐条检查。

---

*SPEC v0.4 — 待迭代*
