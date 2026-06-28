# manga-translator-ui 生态对比分析

> 对比仓库: [hgmzhn/manga-translator-ui](https://github.com/hgmzhn/manga-translator-ui)
> 分析日期: 2026-06-27
> 目的: 深度对比生态差异，明确扬弃（采纳/拒绝/改造）

## 仓库概况

| 维度 | manga-translator-ui | mga |
|------|---------------------|-----|
| 定位 | 漫画翻译 Photoshop（产品级工具） | 漫画翻译大脑（智能层） |
| Stars | 1940+ | — |
| 前身 | zyddnys/manga-image-translator fork | 独立项目，以 manga-image-translator 为 runtime |
| 界面 | PyQt6 桌面 UI + FastAPI Web 服务器 | CLI |
| 许可证 | GPL-3.0 | — |
| 核心差异 | 端到端单体翻译工具，强交互/UI | 6 层 pipeline + 双层架构（host + runtime），强 QA/记忆/文化适配 |

### 架构对比

```
manga-translator-ui (单体)        mga (双层)
┌──────────────────────┐          ┌────────────────────┐
│  PyQt6 UI / FastAPI  │          │  CLI / (future Web)│
│  ┌────────────────┐  │          ├────────────────────┤
│  │  翻译/OCR/修复  │  │          │  mga host layer    │ ← 智能层（LLM 编排/QA/记忆）
│  │  (全部在一个进程) │  │          │  (Python, 轻量)    │
│  └────────────────┘  │          ├────────────────────┤
└──────────────────────┘          │  manga_translator  │ ← runtime（PyTorch 检测/OCR/修复/渲染）
                                  │  (subprocess, 重量) │
                                  └────────────────────┘
```

这个架构差异是下面所有扬弃判断的根基 — manga-translator-ui 的很多设计决策来自「单体进程」假设，直接搬到 mga 的「双层 subprocess」架构可能是错误的。

## 生态差异总览

| 能力 | manga-translator-ui | mga 现状 | 判定 |
|------|---------------------|---------|------|
| Docker 部署 | CPU/GPU 双版本 multi-stage | 无 Docker 化 | **扬**: BUILD_TYPE 切换 + 空卷恢复 |
| API Key 轮转 | 30 slot round-robin + failover | ProviderCascade 跨 provider fallback，单 key | **扬**: 同 provider 多 Key；**弃**: 全局 dict |
| 多模态 OCR | PaddleOCR-VL 本地 + API per-region | vision stage 页级 + 5 恢复策略 + 幻觉检测 | **改**: 补 per-region OCR；**弃**: 本地 VLM |
| 子进程内存管理 | psutil + batch 重启 + Queue | subprocess.run() 无 timeout/无监控 | **扬**: timeout + 优雅退出；**弃**: multiprocessing |
| HQ 文本渲染 | upscale-then-downscale (2-4x) | freetype 直出（小字号差） | **扬**: 几行代码，效果显著 |
| AI 驱动渲染 | OpenAI/Gemini 图像生成渲染文字 | 无 | **弃（当前）**: 成本/可控性不足 |
| 并发管线 | 4 线程 stage 间流水线 | 串行 + 可选页间并行 | **弃**: 有状态管线不适合 |
| 气泡感知合并 | YOLO + NetworkX + Shapely | vision stage box_type LLM 推断 | **弃实现/扬思路** |
| 文本替换引擎 | 方向感知替换 (YAML 配置) | QA StylePolish（翻译后检查） | **扬**: 竖排→横排标点是正确性问题 |
| 术语提取 | 单次 LLM glossary 提取 | 4 阶段 CoinageDetector + 7 级分类 | **弃**: mga 更优；**扬**: 反提取黑名单 |
| 可视化编辑器 | PyQt6 MVC + Command Pattern | 无 | **弃**: PyQt6；**扬**: Command Pattern 思路 |
| HQ 多模态翻译 | image + JSON → 单次 LLM | vision 解耦 → 纯文本翻译 | **弃**: mga 解耦设计更优 |
| 服务端 | FastAPI + 鉴权/配额/管理 | WEB_API_SPEC.md 已规划 | 参考但不照搬 |

---

## 深度调查与扬弃分析

### 1. Docker 化

#### 他们怎么做的

**双版本 multi-stage build**:

```dockerfile
# 通过 ARG BUILD_TYPE=cpu|gpu 切换基础镜像
FROM python:3.12-slim AS base-cpu
FROM nvidia/cuda:12.1.0-cudnn8-runtime AS base-gpu
FROM base-${BUILD_TYPE} AS base
```

**关键设计决策**:

- **默认数据备份**: build 阶段 `cp -r /app/fonts /app/default_fonts`，entrypoint 启动时检查挂载卷是否为空，空则从备份恢复
- **7 个持久化卷**: fonts、dict、result、models、logs、server data、config 分开挂载
- **内存限制**: CPU 版 8G limit/2G reservation，GPU 版 16G limit/4G reservation + NVIDIA device reservation
- **健康检查**: `curl -f http://localhost:8000/` 每 30s，start_period 60s
- **QT_QPA_PLATFORM=offscreen**: 无头 Qt 渲染
- **pydensecrf 从源码编译**: pip 安装会失败

**docker-compose 结构**:

```yaml
services:
  manga-translator-cpu:
    mem_limit: 8g
    mem_reservation: 2g
    mem_swappiness: 60
    volumes:
      - fonts:/app/fonts
      - models:/app/models

  manga-translator-gpu:
    mem_limit: 16g
    mem_reservation: 4g
    deploy:
      resources:
        reservations:
          devices:
            - capabilities: [gpu]
```

#### mga 现状

- 零 Docker 基础设施
- 安装方式: `pip install -e ".[dev]"`
- 桌面分发有 PyInstaller 冻结 (~140 MB thin shell)，但不含 PyTorch
- 模型权重通过 `models/` 符号链接管理（detection/*.ckpt, inpainting/*.ckpt, ocr/*.ckpt），共数百 MB 到 GB
- GPU 依赖: PyTorch, torchvision, ONNX Runtime, transformers, manga-ocr, open_clip_torch
- 平台限制: pydensecrf 仅 Linux; freetype-py 需要系统库

#### 扬弃判定

| 要素 | 判定 | 理由 |
|------|------|------|
| `BUILD_TYPE` ARG 双版本切换 | **扬** | 最简洁的 CPU/GPU 双版本方案，直接可用 |
| 默认数据备份 + entrypoint 空卷恢复 | **扬** | 解决 Docker 化的常见陷阱（字体/模型挂载空卷），直接可抄 |
| 持久化卷分离 | **改** | mga 需要的卷不同：models、configs、output、memory-state（不需要 fonts/dict/server data） |
| 内存限制配置 | **扬** | 8G/16G 分档 + `mem_swappiness: 60` 是合理默认值 |
| `QT_QPA_PLATFORM=offscreen` | **弃** | mga 的 runtime 不直接使用 Qt 渲染（通过 subprocess 调用），这个 env var 应该设在 runtime subprocess 内部 |
| pydensecrf 源码编译 | **扬** | mga 也依赖 pydensecrf，同样的编译问题会出现 |
| 7 个持久化卷 | **弃** | 过度设计。mga 作为 CLI 工具，4 个卷足够（models、configs、output、memory-state） |
| 健康检查 curl | **弃** | mga 当前是 CLI 工具不是 web 服务，无 HTTP 端点可检查。未来加 Web API 后再考虑 |

#### mga 的 Docker 化特殊挑战

manga-translator-ui 是单体应用，一个镜像一个进程。mga 是双层架构:

```
Container
├── mga host (pip install -e .)        ← 轻量 Python，LLM API 调用
└── manga_translator runtime           ← 重量 PyTorch，GPU 推理
    └── models/ (符号链接 → 卷挂载)
```

mga 的 `runtime_bridge/external.py` 用 `subprocess.run(["python", "-m", "manga_translator", ...])` 调用 runtime，容器内两层共享同一个 Python 环境。这意味着 Dockerfile 必须同时安装 mga 的 LLM 依赖和 runtime 的 PyTorch 依赖。

---

### 2. API Key 轮转

#### 他们怎么做的

**核心数据结构** (`api_key_rotation.py`, ~350 行):

```python
@dataclass(frozen=True)
class APIEndpoint:
    feature: str      # "translator" | "ocr" | "colorizer"
    provider: str     # "openai" | "gemini"
    slot: int         # 1, 2, 3...
    api_key: str
    base_url: str
    model_name: str
    status_key: str   # "translator:openai:1:https://api.openai.com:gpt-4o"
    label: str
```

**两种轮转策略**:

| 策略 | 行为 | 适用场景 |
|------|------|---------|
| `failover`（默认） | 按顺序尝试，失败后切下一个 | 稳定性优先 |
| `round_robin` | 轮询分配请求，游标跟踪位置 | 吞吐量优先 |

**环境变量自动发现**:

```
OPENAI_API_KEY      → slot 1
OPENAI_API_KEY_2    → slot 2
OPENAI_API_KEY_3    → slot 3
OPENAI_API_BASE_2   → slot 2 base URL
OPENAI_MODEL_2      → slot 2 model
```

`get_rotation_slot_count()` 自动扫描 `_2`, `_3`... 后缀，上限 `MAX_ROTATION_SLOTS=30`。

**状态管理（进程内全局 dict）**:

```python
_API_STATUS: dict[str, dict] = {}

state = "available" | "cooldown" | "unavailable" | "failed"
```

- 400/402/404/quota exceeded → `unavailable`（永久跳过）
- 429/rate limit → `cooldown`（解析 Retry-After，冷却后复用）
- 临时错误 → `failed`（允许继续重试）

**调用层封装**:

```python
await run_with_api_candidates(
    endpoints=settings.candidates,
    strategy="round_robin",
    operation=_with_endpoint,
    retry_attempts=3,
    on_candidate_error=callback,
)
```

#### mga 现状

- **每个 provider 严格绑定一个 key** — TOML 配置 `api_key_env` 是单值字符串，无 list/array
- **ProviderCascade** 是跨 provider fallback（primary → fallback → local），不是同 provider 多 Key
- **重试**: OpenAI provider 用 SDK 自带的 `max_retries=2`，其他 provider 无重试逻辑
- **无 rate-limit 感知**: 无配额追踪、无预判切 Key、无 cooldown

#### 扬弃判定

| 要素 | 判定 | 理由 |
|------|------|------|
| 环境变量 `_2`/`_3` 自动发现 | **扬** | 零配置文件改动，用户体验好，直接可实现 |
| round_robin 策略 | **扬** | 批量翻译几百页时，单 Key RPM 限制是实际瓶颈，round_robin 是刚需 |
| Key 四态状态机 | **扬** | available/cooldown/unavailable/failed 覆盖了所有实际场景 |
| Retry-After header 解析 | **扬** | 精确等待而非盲重试，减少不必要的失败 |
| 永久错误识别（400/402/404） | **扬** | 避免浪费重试次数在已死 Key 上 |
| 进程内全局 `_API_STATUS` dict | **弃** | mga 的 LLM 调用在 host 进程，但 runtime OCR 在 subprocess — 全局 dict 无法跨进程共享。mga 应该用 provider 实例内部状态，不是模块级全局变量 |
| `feature` 维度（translator/ocr/colorizer） | **弃** | mga 的 stage 划分不同（vision/translation/QA/render），不需要照搬 feature 分类 |
| `run_with_api_candidates()` 统一编排器 | **改** | 思路好但 mga 应该在 `ProviderCascade.call_chat()` 内部实现，而非独立函数。每个 provider 内部维护自己的 Key 池 |
| MAX_ROTATION_SLOTS=30 | **弃** | 过度设计。实际使用中 2-5 个 Key 足够，上限 10 个即可 |

#### 关键架构区分

manga-translator-ui 的 Key 轮转和 mga 的 ProviderCascade 是**正交的两层**:

```
mga 应该的架构:

ProviderCascade                        ← Layer 1: 跨 provider 容错
├── OpenAI Provider                    ← Layer 2: 同 provider Key 池
│   ├── Key slot 1 (OPENAI_API_KEY)
│   ├── Key slot 2 (OPENAI_API_KEY_2)  ← round_robin / failover
│   └── Key slot 3 (OPENAI_API_KEY_3)
├── Anthropic Provider
│   ├── Key slot 1
│   └── Key slot 2
└── Gemini Provider (local fallback)
    └── Key slot 1
```

Layer 1 (ProviderCascade) 已有。Layer 2 (同 provider 多 Key) 需要新增。两者叠加才完整。

---

### 3. 多模态 OCR

#### PaddleOCR-VL（本地推理）

来源: `ocr/model_paddleocr_vl.py`, ~500 行

**核心流程**:

```
检测到的文本区域 → 裁剪+旋转对齐 → _recognize_single(region_img, prompt)
    → VLM 推理 (PaddleOCR-VL-1.6, ~3B 参数)
    → 幻觉检测 + 3 轮递进重试
    → 48px 模型估算前/背景色
```

**幻觉防御三层检测**:

```python
def _looks_like_repeated_hallucination(self, text):
    # 1. 单字符重复 20+ (如 "。" × 20)
    if re.search(r"(.)\1{19,}", compact): return True
    # 2. 短模式重复 8+ (如 "ああ" × 8)
    if re.search(r"(.{2,8})\1{7,}", compact): return True
    # 3. 标点占比 > 65% 且最常见字符占比 > 45%
```

**递进重试配置**:

| 轮次 | max_new_tokens | repetition_penalty | no_repeat_ngram_size | prompt 后缀 |
|------|----------------|-------------------|---------------------|-------------|
| 1 | 128 | — | — | — |
| 2 | 64 | 1.15 | 4 | "Output ONLY the text." |
| 3 | 48 | 1.25 | 3 | "Only output the exact text." |

#### API OCR（OpenAI/Gemini per-region）

```python
class ModelOpenAIOCR(BaseAPIOCR):
    API_KEY_ENV = "OCR_OPENAI_API_KEY"
    FALLBACK_API_KEY_ENV = "OPENAI_API_KEY"  # 分层 Key 查找

class ModelGeminiOCR(BaseAPIOCR):
    API_KEY_ENV = "OCR_GEMINI_API_KEY"
    FALLBACK_API_KEY_ENV = "GEMINI_API_KEY"
```

- 每个文本区域裁剪为 PNG base64 → 单独发给 API
- `asyncio.Semaphore` 控制并发
- 集成 Key 轮转

#### mga 现状

mga 在 OCR 恢复和幻觉检测方面**已经有丰富积累**，不是白纸一张:

- **5 种恢复策略**: SWITCH_OCR_MODEL, ADJUST_THRESHOLD, HYBRID_MODE, CONTINUE, ABORT — 但全是**页级或 pipeline 级**，无 per-region
- **BlankPageDetector**: 检测连续空白页（每个 bubble 的 source_text < 3 字符 × 连续 3 页），触发恢复
- **Vision bubble 幻觉检测**: `_validate_vision_bubble` 拒绝空文本、零/微小 bbox、off-page bbox、字符集 Jaccard 不匹配；`_cross_page_bleed_check` 用最长公共子串比率检测跨页泄漏
- **Render stage 白区域检测**: `_is_blank_region` 用像素分析拒绝落在空白/白色区域的 OCR 结果；低置信度过滤 (`ocr_min_prob=0.25`)
- **OCR 引擎**: Tesseract, MOCR (manga-ocr), MIT OCR (32px/48px/48px_ctc，在 runtime subprocess 内推理)

**关键缺口**: 所有恢复策略都是**页级**的。如果一页上 8 个区域中有 1 个 OCR 失败，mga 没有机制单独重试那一个区域。

#### 扬弃判定

| 要素 | 判定 | 理由 |
|------|------|------|
| per-region API OCR（裁剪区域 → API） | **扬** | mga 缺的正是这个粒度。作为 `RecoveryOrchestrator` 的第 6 种策略加入: `PER_REGION_API_OCR`，对 OCR 结果为空或低置信度的区域，裁剪后发给 GPT-4o/Gemini |
| 重复模式幻觉正则 | **改** | mga 已有 vision bubble 幻觉检测（Jaccard, bbox 校验），但缺少**文本重复模式**检测。补充这组正则到 `BlankPageDetector` 作为补充信号，而非替代现有检测 |
| 递进重试策略（收紧 generation_config） | **弃** | 这是本地 VLM 推理的调参技巧，mga 不跑本地 VLM OCR（OCR 在 runtime subprocess），不适用 |
| PaddleOCR-VL 本地部署 | **弃** | 引入 3B 参数本地模型增加部署复杂度（额外 6GB+ VRAM），且 mga 已有 MOCR + MIT OCR + vision stage 三层覆盖，ROI 不足 |
| 分层 Key 查找（OCR_OPENAI_API_KEY → OPENAI_API_KEY） | **扬** | 允许不同 stage 用不同 Key，避免配额争抢。TOML 配置加 `vision_api_key_env`, `translation_api_key_env` 字段 |
| asyncio.Semaphore 并发控制 | **扬** | mga 的 vision stage 和未来的 per-region OCR 都需要并发控制，防止 API rate limit |
| 48px 色彩估算模型 | **弃** | manga-translator-ui 用 48px 模型估算前/背景色是因为它需要在图上渲染文字时匹配颜色。mga 的渲染由 runtime 处理，host 层不需要色彩信息 |

#### mga 已有能力 vs 外部仓库对照表

| 能力 | manga-translator-ui | mga | 结论 |
|------|---------------------|-----|------|
| 页级 OCR 恢复 | 无（按区域处理） | 5 种策略 | mga 更强 |
| 区域级 OCR 恢复 | per-region API OCR | 无 | 需补齐 |
| 幻觉检测（文本重复） | 正则三层检测 | 无 | 需补齐（补充到现有检测链） |
| 幻觉检测（语义/空间） | 无 | Jaccard + bbox 校验 + 跨页泄漏 + 白区域像素分析 | mga 更强 |
| 本地 VLM OCR | PaddleOCR-VL (3B) | 无（依赖 runtime OCR + vision stage） | 弃（ROI 不足） |
| 并发控制 | asyncio.Semaphore | 无 | 需补齐 |

---

### 4. 子进程内存管理

#### 他们怎么做的

来源: `mode/subprocess_manager.py`, ~250 行

```
主进程 (translate_with_subprocess)
    ├─ 启动子进程 batch 1 (50 张图)
    │   ├─ 每张图后: psutil.Process().memory_info().rss > 8GB? → 提前退出
    │   │           psutil.virtual_memory().percent > 80%? → 提前退出
    │   └─ multiprocessing.Queue 返回 {completed, failed}
    ├─ 子进程退出 → PyTorch/CUDA 内存全部释放
    ├─ 启动子进程 batch 2 (剩余 50 张)
    └─ 所有完成或全部失败
```

**双重内存阈值**:

| 阈值 | 默认值 | 作用 |
|------|-------|------|
| `memory_limit_mb` | 0（禁用） | 进程 RSS 绝对值 |
| `memory_limit_percent` | 80% | 系统总内存占比，防 OOM killer |

**优雅退出三段式**: `join(30)` → `terminate()` → `join(5)` → `kill()`

**超时**: `len(batch_files) * 600` 秒（每图 10 分钟）

#### mga 现状

**严重缺口**:

1. **subprocess.run() 无 timeout**: 三个 runtime 入口（`run_external_translation_runtime`, `run_export_artifact`, `run_render_only`）全部省略 `timeout=` 参数。runtime 挂起（GPU 死锁、无限循环）时，mga 进程**永久阻塞，无恢复路径**
2. **无父进程侧内存监控**: psutil 已在 `pyproject.toml` 依赖中，但仅在 `manga_translator/` 内部使用（runtime 自己监控自己）。mga host 层**对 runtime 子进程的内存完全不可见**
3. **无优雅退出**: subprocess.run() 不支持中途 terminate，runtime 崩溃时只能等 returncode
4. **BatchProcessor 无内存感知**: `mga/pipeline/batch.py` 用 ThreadPoolExecutor 做多章节并行，失败章节标记为 `"failed"` 继续处理，但无内存检查、无子进程重启
5. **有 RestartPipelineSignal**: orchestrator 支持 max 1 次 pipeline 重启（用于 OCR model 切换），但不是内存驱动的

**runtime 内部有简单保护**: `manga_translator/mode/local.py` 在 85%/90% 内存时触发 `gc.collect()` + `torch.cuda.empty_cache()`，但这是**自救**（在子进程内），mga 父进程不知道。

#### 扬弃判定

| 要素 | 判定 | 理由 |
|------|------|------|
| subprocess timeout 参数 | **扬（紧急）** | 当前无 timeout = 可能永久阻塞。最低改动: `subprocess.run(..., timeout=page_count * 300)` |
| 优雅退出三段式 | **扬** | join → terminate → kill 是标准做法，直接可用。但需要先把 subprocess.run 改为 Popen |
| subprocess.run → Popen 改造 | **扬** | Popen 支持 timeout + terminate + 实时 stdout 流式读取，是子进程管理的基础 |
| 父进程侧 psutil 内存监控 | **扬** | `psutil.Process(pid).memory_info().rss` 从外部监控 runtime 内存，不侵入 runtime 代码 |
| multiprocessing.Process 架构 | **弃** | manga-translator-ui 把**整个翻译器**封装成 `worker_translate_batch()` 跑在 `multiprocessing.Process` 里。mga 不能这么做 — mga 的智能层（翻译/QA/记忆/文化适配）在 host 进程，只有 runtime 是 subprocess。用 multiprocessing.Process 包装 runtime 调用是过度设计，Popen 足够 |
| multiprocessing.Queue 通信 | **弃** | mga 的 runtime 通过文件系统交换数据（`.mga-payload/pages.json`, `artifact-NNNN.json`），不需要 Queue。文件系统契约已稳定，改为 Queue 是无意义的架构变更 |
| batch_per_restart=50 固定重启 | **改** | 思路好（防缓慢泄漏），但 mga 的粒度应该是**每章节重启**而非每 50 张。在 `batch.py` 的章节循环间插入 runtime 健康检查即可 |
| 双重内存阈值 | **改** | 绝对值 + 百分比双保险是好设计，但默认值需要调整 — mga 的 runtime 单页处理峰值 ~2-4GB（检测+OCR+修复），不像 manga-translator-ui 那样累积状态，阈值可以更低 |
| completed_files 断点续传 | **弃** | mga 的 BatchProcessor 已经有 `batch_progress.json` 实现了断点续传，不需要额外机制 |

#### 架构适配方案

manga-translator-ui 的做法（整个翻译器在子进程重启）不适合 mga，但思路可以改造:

```
manga-translator-ui 的做法:              mga 应该的做法:
┌─────────────────────┐                 ┌──────────────────────┐
│ 主进程 (UI/CLI)      │                 │ mga host (不重启)     │
│   ↓                 │                 │   ├─ translation     │ ← LLM 调用，内存稳定
│ multiprocessing.    │                 │   ├─ QA              │
│ Process(translator) │                 │   ├─ memory          │
│   ↓ 每50张重启      │                 │   └─ runtime_bridge  │
└─────────────────────┘                 │       ↓ subprocess   │
                                        │     Popen(runtime)   │ ← 仅重启这一层
                                        │       ↓ 每章节检查    │
                                        │     内存 > 阈值?     │
                                        │       ↓ 是           │
                                        │     terminate + 新 Popen │
                                        └──────────────────────┘
```

---

### 5. 可视化编辑器架构

#### 他们怎么做的

**MVC + Command Pattern + Service Mixin**:

```
EditorController (64KB)
    ├── DocumentService mixin   — 文档加载/保存 (13KB)
    ├── ExportService mixin     — PSD/多格式导出 (27KB)
    ├── InpaintService mixin    — 修复操作 (18KB)
    │
    ├── EditorModel (7KB)       — regions, current_image, undo/redo stacks
    ├── EditorLogic (13KB)      — 坐标变换/区域计算
    │
    └── View 层
        ├── GraphicsView (8KB)         — QGraphicsView
        ├── GraphicsViewInput (33KB)   — 鼠标/键盘事件
        ├── GraphicsItems (59KB)       — 文本框/蒙版可视元素
        ├── SelectionManager (9KB)     — 选中状态
        ├── ShortcutManager (13KB)     — 快捷键
        ├── PropertyPanel (98KB)       — 属性面板（最大组件）
        └── FileListView (49KB)        — 文件列表
```

**Command Pattern（撤销/重做）**:

```python
class BaseCommand:
    def execute(self): ...
    def undo(self): ...

class MoveRegionCommand(BaseCommand): ...
class EditTextCommand(BaseCommand): ...
class InpaintCommand(BaseCommand): ...
```

**渲染管线**:

```
RenderCoordinator
    ├── RenderLayoutPipeline    — 布局计算
    ├── TextRenderPipeline      — 文本渲染
    ├── TextRendererBackend     — FreeType/Pillow 后端
    └── GeometryCommitPipeline  — 几何变换提交
```

#### 扬弃判定

| 要素 | 判定 | 理由 |
|------|------|------|
| PyQt6 技术栈 | **弃** | mga 定位是 CLI + 未来 Web。PyQt6 桌面应用路线与 mga 方向不符，且 GPL-3.0 许可证限制 |
| Command Pattern（撤销/重做） | **扬（设计思路）** | 如果做 Web 编辑器，这是标准做法。前端 Redux/Zustand action 天然就是 command |
| RenderCoordinator 管线分离 | **扬（设计思路）** | 「布局计算」与「文本渲染」分离的思路可迁移到 mga 的 render_stage，但不照搬实现 |
| Service Mixin 拆分 | **弃** | EditorController 64KB = 上帝对象用 mixin 分拆，是被迫的妥协而非好设计。Web 版应该用组合而非继承 |
| GraphicsItems (59KB) | **弃（实现）** | QGraphicsItem 是 Qt 专有 API。Web 版用 Fabric.js/Konva.js canvas 库替代，架构完全不同 |
| PropertyPanel (98KB) | **弃（实现）/扬（需求规模预警）** | 作为实现不可用（Qt widgets），但作为**工作量信号**有价值 — 属性编辑是最重的 UI 工作，提前预估 |
| FileListView (49KB) | **弃** | Qt 文件管理 UI，Web 版用标准 file browser 组件 |
| MVC 整体架构 | **弃** | mga 的 Web 编辑器更适合 React + 状态管理（Zustand/Jotai），而非传统 MVC |

#### 核心判断

可视化编辑器是**最不值得当前投入**的方向:
1. mga 的核心价值在智能层（QA/记忆/文化适配），不在交互编辑
2. 编辑器的 UI 工作量极大（PropertyPanel 98KB 说明问题），且与 mga 核心能力无协同
3. 如果用户需要编辑，可以直接用 manga-translator-ui 的桌面编辑器处理 mga 的输出

---

## HQ 多模态翻译 — 扬弃分析

### 他们的做法

```
OCR 区域 → draw_text_boxes_on_image()（彩色编号框）
         → encode_image（resize ≤1024px, base64 PNG）
         → image + JSON [{id, text}] → 单次 LLM 调用
         → parse_hq_response()（从混合文本提取 JSON）
         → 降级: content_filter/502/429 → send_images=False
```

三段式翻译: LITERAL → ANALYSIS → POLISHING
五原则: FIDELITY > NATURAL EXPRESSION > CHARACTER CONSISTENCY > CULTURAL NATURALNESS > FULL TRANSLATION

### mga 的做法

```
Pass 1 (vision stage): 整页图片 → vision LLM → 结构化元数据提取
  输出: source_text, bbox, box_type, provisional_speaker, voice_hint, confidence

Pass 2 (translation stage): 纯文本 → translation LLM → 翻译
  输入: source_text + character_profiles + scene_summary + cultural_context
        + relationship_data + voice_hints + vision_ctx (全是文本，无图片)
```

### 扬弃判定

| 要素 | 判定 | 理由 |
|------|------|------|
| 翻译时发送原图 | **弃** | mga 的 vision/translation **解耦是主动的架构选择**，不是缺失。原因: (1) vision 一次提取，下游多 stage 复用元数据，不重复烧 vision tokens; (2) 翻译 LLM 不需要看图就能翻译，视觉上下文已通过 voice_hint/box_type/speaker 结构化传递; (3) 解耦允许 vision 和 translation 用不同模型（vision 用便宜的 Gemini，translation 用强的 GPT-4o） |
| 图上画彩色编号框 | **弃** | 这是为了让 LLM 理解"哪段文字在哪个位置"。mga 的 vision stage 已经输出了 bbox 坐标，不需要在图上画框 |
| 三段式翻译 prompt | **改** | LITERAL → ANALYSIS → POLISHING 的思路可以参考，但 mga 的翻译已经有两步（语义提取 → persona 渲染），且有 QA 层做 6+ 维度的后处理校验。三段式做在一次 LLM 调用里效果不如 mga 的多 stage 管线 |
| 降级机制（关闭图片发送） | **弃** | mga 的 vision stage 独立于 translation stage，vision 失败不影响翻译 — 翻译会退化到纯 OCR 文本，但不需要特殊降级逻辑 |
| content_filter 处理 | **扬（防御模式）** | 漫画内容确实会触发安全过滤。manga-translator-ui 的做法是检测到 content_filter 后关闭图片改纯文本。mga 的 vision stage 应该有类似降级: vision 调用被安全拒绝时，标记该页为 vision-skipped 继续流程 |

### 核心判断

mga 的 vision + translation 解耦 **优于** manga-translator-ui 的单次多模态调用:

| 维度 | HQ 模式（manga-translator-ui） | 解耦模式（mga） |
|------|-------------------------------|----------------|
| Token 成本 | 每页翻译都烧 vision tokens | vision 一次，翻译纯文本 |
| 翻译质量 | 视觉上下文直接可用 | 视觉上下文通过元数据间接传递 |
| 管线灵活性 | 翻译强耦合于视觉 | vision/translation 可独立选模型/重试/优化 |
| QA 可插入性 | QA 必须在同一次 LLM 调用内 | QA 是独立 stage，9 个 proofreader 分别运行 |
| 记忆/文化适配 | 在 system prompt 里塞 glossary | 独立的 MemoryService + CulturalService 注入 |
| 降级鲁棒性 | 图片被安全过滤 → 全部降级 | vision 失败 → 仅 vision 降级，翻译正常 |

**结论: 不要学 HQ 模式。mga 已有的方式更好。**

---

## 补充方向：初版遗漏的高关联特性

初版分析聚焦基础设施（Docker/Key/子进程），遗漏了**直接影响翻译输出质量**的渲染和管线特性。第二轮全面扫描后补充如下。

### 6. HQ 文本渲染（upscale-then-downscale）

#### 他们怎么做的

来源: `text_render_hq.py`

核心技巧: 在目标尺寸的 2-4 倍分辨率上渲染文字，再用 LANCZOS 降采样回目标尺寸。

```
字体大小 < 15px → 4x 上采样渲染 → LANCZOS 降采样
字体大小 < 25px → 3x 上采样渲染 → LANCZOS 降采样
字体大小 < 35px → 2x 上采样渲染 → LANCZOS 降采样
字体大小 ≥ 35px → 直接渲染（无需上采样）
```

解决了 freetype 在小字号下抗锯齿不足、定位误差大的问题。

#### mga 现状

mga 的 runtime (`manga_translator/rendering/text_render.py`) 使用 freetype Python 绑定直接渲染。已知弱点:
- 小字号抗锯齿差
- 无 OpenType 特性支持
- 无自适应字号调整
- 字体回退链简单（按路径查找，无智能选择）

**这是 mga 输出质量链上最弱的一环** — 智能层（QA/记忆/文化适配）再强，最终用户看到的是渲染后的图片。

#### 扬弃判定

| 要素 | 判定 | 理由 |
|------|------|------|
| upscale-then-downscale 技巧 | **扬** | 直接可用于 runtime 的 `text_render.py`。改动很小（渲染前乘系数，渲染后 resize），效果显著 |
| 字号分档系数选择 | **扬** | 15/25/35px 分界点 + 4x/3x/2x 系数是经过实践调优的，不需要自己摸索 |
| LANCZOS 降采样 | **扬** | PIL/Pillow 自带，`Image.resize(..., Image.LANCZOS)` |

**改造难度: 极低**。这是本文档中 ROI 最高的单项改进 — 几行代码改动，渲染质量立竿见影。

---

### 7. AI 驱动渲染（model_api_renderer）

#### 他们怎么做的

来源: `manga_translator/rendering/model_api_renderer.py` + `ai_image_preprocess.py`

完全不同的渲染路线: 不用 freetype，而是用 OpenAI/Gemini 的**图像生成 API** 来渲染翻译文本。

```
修复后的漫画页（已去除原文）
    ↓
裁剪目标区域 → 正方形 padding（API 要求）
    ↓
多模态 prompt: "在这个区域内渲染以下文字: [翻译]，风格匹配周围画风"
    ↓
API 返回渲染后的区域图片
    ↓
粘贴回原图
```

#### 扬弃判定

| 要素 | 判定 | 理由 |
|------|------|------|
| AI 渲染作为主要路径 | **弃** | 成本极高（每个区域一次图像生成 API 调用），风格一致性不可控，延迟大 |
| AI 渲染作为兜底/增强 | **改（长期观察）** | 对于艺术字体、手写风格等 freetype 无法处理的场景，AI 渲染可以作为**可选增强**。但当前图像生成 API 的可控性不足以保证文字清晰度，等技术成熟再考虑 |
| 正方形 padding 预处理 | **弃** | API 特定的 workaround，不通用 |

---

### 8. 并发管线（4 线程独立流水线）

#### 他们怎么做的

来源: `concurrent_pipeline.py`

```
Thread 1: Detection + OCR  ──→ Queue ──→
Thread 2: Translation      ──→ Queue ──→
Thread 3: Inpainting       ──→ Queue ──→
Thread 4: Rendering        ──→ Output
```

4 个 stage 各跑在独立线程上，通过背压限制队列连接。页面 A 在渲染时，页面 B 在翻译，页面 C 在检测 — 流水线并行。

#### mga 现状

- 默认**串行**处理（每页完整走完 7 stage 后处理下一页）
- 可选 `semantic-parallel`（Phase 1）和 `batch-parallel`（Phase 2），但粒度是**页间并行**，不是 stage 间流水线
- `batch.py` 多章节处理用 `ThreadPoolExecutor`

#### 扬弃判定

| 要素 | 判定 | 理由 |
|------|------|------|
| stage 间流水线并行 | **弃** | mga 的架构不适合。原因: (1) mga 的 stage 之间有复杂依赖（vision → character+culture → translation → QA），不像 manga-translator-ui 那样 stage 独立; (2) mga 的 runtime 调用是 subprocess，天然是阻塞的全页操作; (3) mga 的记忆系统需要按页顺序更新（前页的角色推断影响后页的翻译） |
| 背压队列 | **弃** | 流水线不采用则队列无意义 |
| 独立线程 + event loop | **弃** | mga 的 LLM 调用已经是异步的（通过 provider 的 async API），不需要额外线程隔离 |

**核心判断**: manga-translator-ui 的 4 线程模型是为**无状态页处理**设计的（检测→翻译→修复→渲染，每页独立）。mga 的管线是**有状态**的（记忆系统、角色图谱、文化适配上下文跨页积累），流水线并行会破坏状态一致性。mga 的页间并行（semantic-parallel）是正确的并发粒度。

---

### 9. 气泡感知文本行合并

#### 他们怎么做的

来源: `textline_merge/__init__.py`

用 NetworkX 图 + Shapely 几何计算，按气泡类型分组检测到的文本行:

```
检测到的文本行 (Quadrilateral[])
    ↓
MangaLens YOLO 模型 → 气泡分类 (balloon, qipao, changfangtiao, other)
    ↓
Shapely 判断: 哪些文本行在哪个气泡内
    ↓
NetworkX 图: 同气泡内的文本行连边
    ↓
按气泡类型应用不同合并策略
    ↓
输出: 合并后的文本区域
```

#### mga 现状

- 文本行合并由 **runtime** 处理（`manga_translator/detection/` 内部），mga host 层不参与
- mga 的 vision stage 输出 `box_type` (bubble/sfx/sign/narration)，但这是 LLM 推断的，不是几何检测的
- 没有 YOLO 气泡检测模型

#### 扬弃判定

| 要素 | 判定 | 理由 |
|------|------|------|
| MangaLens YOLO 气泡检测 | **改（观察）** | 有价值但引入新模型增加部署复杂度。可以先用 mga 现有的 vision stage `box_type` 推断替代 — LLM 识别气泡类型的准确率已经足够好 |
| NetworkX + Shapely 几何合并 | **弃** | 这是在 runtime 检测层做的工作。mga 的 host 层不应该重做检测层的文本行合并 — 这会侵入 runtime 的职责边界 |
| 按气泡类型差异化合并策略 | **扬（思路）** | mga 可以在 vision stage 根据 `box_type` 调整验证和过滤策略（如 SFX 区域容忍更短的 source_text） |

---

### 10. 方向感知文本替换引擎

#### 他们怎么做的

来源: `text_replacements.py`

在渲染前对翻译文本做系统性替换:

```yaml
# 方向感知: 竖排和横排用不同替换规则
vertical:
  - pattern: "「"
    replacement: "﹁"   # 竖排引号
  - pattern: "（"
    replacement: "︵"   # 竖排括号
horizontal:
  - pattern: "·"
    replacement: "・"   # 中点统一
```

支持正则和字面量两种匹配，从 YAML 配置文件加载。

#### mga 现状

- QA 层的 `StylePolish` proofreader 做标点/格式/可读性校验，但是在翻译**之后**检查，不是在渲染**之前**替换
- 无方向感知（竖排 vs 横排）的标点替换
- `speaker_filter` 用模式匹配过滤描述性文本，但不处理标点规范化

#### 扬弃判定

| 要素 | 判定 | 理由 |
|------|------|------|
| 竖排/横排方向感知标点替换 | **扬** | 日漫竖排到中文横排时标点符号需要转换（「」→ ""），这是翻译正确性问题，不只是风格问题。可以加到 render_stage 的 payload 构建中 |
| YAML 配置的替换规则 | **扬** | 可配置的规则比硬编码更灵活。mga 可以在 `configs/` 下加一个 `text_replacements.toml` |
| 正则 + 字面量双模式 | **扬** | 覆盖简单替换（字面量）和复杂模式（正则）两种场景 |

**改造难度: 低**。在 render_stage 构建 payload 前加一步文本替换管道。

---

### 11. 术语提取 prompt（Glossary Extraction）

#### 他们怎么做的

来源: `dict/glossary_extraction_prompt.yaml`

用单次 LLM 调用从 OCR 文本中提取专有名词:

```
OCR 文本 → LLM prompt (提取 Person/Location/Org/Item/Skill/Creature)
         → 反提取规则 (排除常见词、OCR 噪声、后缀)
         → 输出: 分类术语列表
```

#### mga 现状

- `CoinageDetector`: 4 阶段流程（detect → propose → confirm → register）自动发现和管理新造词
- `TermClassifier`: 7 级分类（G1 universal → G7 fictional）
- `TerminologyDB`: 每作品术语存储
- `CulturalService`: 完整的文化适配策略

#### 扬弃判定

| 要素 | 判定 | 理由 |
|------|------|------|
| 单次 LLM 术语提取 | **弃** | mga 的 4 阶段 CoinageDetector + 7 级 TermClassifier **远超**简单的单次提取。mga 的方案有确认环节（人工/自动）防止误提取，有分级系统区分通用词和虚构词。这是 mga 的竞争优势，不应该退化到单次提取 |
| 反提取规则 | **扬（补充）** | "排除常见词、OCR 噪声、后缀" 的黑名单可以补充到 CoinageDetector 的 detect 阶段，减少误报 |
| 分类体系 (Person/Location/Org/Item/Skill/Creature) | **弃** | mga 的 G1-G7 分级系统更细致、更有语言学依据 |

---

## mga 的竞争壁垒（不应改变的方向）

对比后更清楚地看到: mga 的核心优势恰恰是 manga-translator-ui **完全没有**的能力。这些是 mga 的护城河，不应该为了对齐外部工具而削弱。

| mga 独有能力 | 外部仓库对应物 | 结论 |
|-------------|-------------|------|
| 9 个 QA proofreader（事实核查/幻觉防护/角色一致性/虚构文字/敬语层级/文化QA/情绪一致性/语言演变/风格润色） | 无 | **护城河**: 多维度后处理校验是翻译质量的根本保证 |
| 4 阶段 Learning Engine（对齐/双视觉/模式提取/验证） | 无 | **护城河**: 从已有翻译中学习是冷启动问题的解法 |
| Knowledge Distillation（Character Card/Lorebook/Hermes Skill 导出） | 无 | **护城河**: 跨工具知识迁移 |
| CulturalService（7 策略 + 敬语补偿 + 造词检测 + 术语分级） | 简单 glossary prompt | **护城河**: 文化适配深度不可同日而语 |
| MemoryService（角色图谱/关系网络/场景记忆/术语库） | 无 | **护城河**: 跨章节一致性的基础 |
| vision + translation 解耦架构 | 耦合的 HQ 模式 | **架构优势**: 更灵活、更省 token、更好降级 |
| 6 种格式适配器（PDF/EPUB/CBZ/CBR/MOBI/Bilingual） | 仅图片 | **广度优势**: 支持电子书全格式 |

---

## 总结：改造优先级路径

| # | 方向 | 改造难度 | ROI | 扬 | 弃 |
|---|------|---------|-----|-----|-----|
| P0 | **HQ 文本渲染** | 极低 | 极高 | upscale-then-downscale 渲染（几行代码，效果显著） | — |
| P0 | **subprocess timeout** | 极低 | 极高 | `subprocess.run(..., timeout=)` | — |
| P0 | **Popen + 优雅退出** | 低 | 高 | join → terminate → kill 三段式 | multiprocessing.Process 架构 |
| P1 | **API Key 轮转** | 低 | 高 | 环境变量自动发现 + round_robin + 四态状态机 | 全局 dict 状态管理; feature 维度 |
| P1 | **文本替换引擎** | 低 | 高 | 方向感知标点替换 + TOML 可配置规则 | — |
| P2 | **Docker 化** | 低 | 中 | BUILD_TYPE 切换 + 空卷恢复 | 7 卷过度设计; 健康检查 (CLI 无 HTTP) |
| P3 | **per-region API OCR** | 中 | 中 | 裁剪区域 → API 回退 + 并发控制 + 分层 Key | PaddleOCR-VL 本地部署; 色彩估算模型 |
| P3 | **幻觉检测正则** | 低 | 中 | 重复模式正则（补充现有检测链） | 递进重试（本地 VLM 调参，不适用） |
| P4 | **运行时内存监控** | 中 | 中 | psutil 父进程侧监控 + 每章节检查 | Queue 通信; 50 张固定重启 |
| — | **HQ 多模态翻译** | — | — | content_filter 降级处理 | 翻译时发图（mga 解耦设计更优） |
| — | **AI 驱动渲染** | — | — | 长期观察（等技术成熟） | 当前成本/可控性不足 |
| — | **并发管线** | — | — | — | mga 有状态管线不适合 stage 间流水线 |
| — | **气泡感知合并** | — | — | box_type 差异化过滤策略（思路） | YOLO 模型引入; 侵入 runtime 职责 |
| — | **术语提取 prompt** | — | — | 反提取黑名单（补充 CoinageDetector） | 单次提取（mga 4 阶段方案更优） |
| — | **可视化编辑器** | 高 | 低（当前） | Command Pattern + RenderCoordinator 思路 | PyQt6 技术栈; Service Mixin; 整体 MVC |
