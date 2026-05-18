# GitHub 漫画翻译开源项目生态调研报告

> 调研时间：2026-05-05  
> 调研范围：GitHub 上与 manga/comic translation 相关的开源项目

---

## 一、核心结论

### 1. 有没有可用的全流程方案？
**有，且至少有 3 个成熟的全流程方案**，覆盖「检测→OCR→擦除→翻译→嵌字」完整 pipeline。

### 2. 嵌字质量如何？
**中等偏上，但远未完美。** 简单场景（日漫竖排文字泡）效果较好；复杂场景（多角度文字、西式漫画、无泡文字）仍有明显缺陷。嵌字质量是当前所有项目的共同短板。

### 3. 能否被包装成 CLI 工具供 agent 调用？
**完全可以。** 首选方案 `manga-image-translator` 已原生支持 CLI + API 模式，是最适合 agent 集成的项目。

---

## 二、项目详细分析

### Tier 1：全流程方案（⭐4000+）

#### 1. zyddnys/manga-image-translator ⭐9845
| 项目 | 详情 |
|------|------|
| **URL** | https://github.com/zyddnys/manga-image-translator |
| **星标** | 9845（最高星漫画翻译项目） |
| **最后更新** | 2026-05-05（活跃） |
| **许可证** | GPL-3.0 |

**核心功能：** 完整的漫画/图片翻译 pipeline，支持 20+ 语言

**技术栈：**
- **文本检测：** CRAFT / comic-text-detector（自研）
- **OCR：** manga-ocr（48px 模型）/ 支持自定义
- **文字擦除：** LaMa Large / AOT-GAN
- **翻译引擎（20+种）：**
  - 在线：OpenAI、DeepSeek、Gemini、Groq、DeepL、Baidu、Youdao、Papago 等
  - 离线：NLLB、Sugoi、M2M100、Qwen2、mBART50、JParaCrawl 等
- **嵌字：** 自研渲染引擎，支持水平/竖排排版

**CLI/API 能力：✅ 原生支持**
```bash
# 本地批量模式
python -m manga_translator local -v -i <path> -l ENG

# Docker CLI 模式
docker run --env="DEEPL_AUTH_KEY=xxx" -v <path>:/app/<path> \
  zyddnys/manga-image-translator:main local -i=/app/<path>

# Web API 模式
cd server && python main.py --use-gpu
# API 地址: http://127.0.0.1:8001
```

**优点：**
- 最成熟的全流程方案，社区最大
- CLI + API + Web 三种模式齐全
- 翻译引擎最丰富（离线+在线全覆盖）
- 配置项极其丰富（JSON 配置文件支持）
- 支持 GPT prompt 自定义、术语表
- Docker 镜像可直接使用

**缺点：**
- 嵌字效果一般，复杂排版场景不够好
- 模型下载体积大（Docker 镜像 ~15GB）
- GPL-3.0 许可证可能有商业限制
- 项目仍自称"早期开发阶段"

---

#### 2. dmMaze/BallonsTranslator ⭐4762
| 项目 | 详情 |
|------|------|
| **URL** | https://github.com/dmMaze/BallonsTranslator |
| **星标** | 4762 |
| **最后更新** | 2026-05-05（活跃） |
| **许可证** | GPL-3.0 |

**核心功能：** 深度学习辅助漫画翻译工具，GUI 为主，支持一键机翻

**技术栈：**
- **底层依赖：** 深度依赖 manga-image-translator（同一作者生态）
- **GUI 框架：** PyQt6
- **OCR/检测/擦除/翻译：** 复用 manga-image-translator 的模块
- **嵌字特色：** 参考原文排版（颜色、轮廓、角度、朝向、对齐方式）

**CLI 能力：✅ 支持 headless 模式**
```bash
python launch.py --headless --exec_dirs "[DIR_1],[DIR_2]..."
```

**优点：**
- GUI 编辑功能强大（掩膜编辑、修复画笔、富文本编辑）
- 支持导入导出 Word 文档
- 排版质量在 GUI 辅助下可以做到很好
- headless 模式可批处理

**缺点：**
- 主要是 GUI 工具，headless 模式文档较少
- 重度依赖 manga-image-translator
- 284 个 open issues
- GPL-3.0 许可证

---

#### 3. mayocream/koharu ⭐4276
| 项目 | 详情 |
|------|------|
| **URL** | https://github.com/mayocream/koharu |
| **星标** | 4276 |
| **最后更新** | 2026-05-05（活跃） |
| **许可证** | GPL-3.0 |
| **语言** | Rust |

**核心功能：** ML-powered 漫画翻译桌面应用，Rust 实现

**技术栈：**
- **推理框架：** candle (Hugging Face) + llama.cpp
- **桌面框架：** Tauri
- **OCR/检测/擦除：** 均为本地 ML 模型
- **翻译：** 本地 LLM 或远程 LLM 后端
- **特色功能：**
  - Codex 图像到图像生成（端到端页面重绘）
  - PSD 分层导出
  - **HTTP API + MCP Server**（用于自动化）

**CLI/API 能力：✅ HTTP API + MCP Server**
- 本地 HTTP API 可供 agent 调用
- MCP Server 支持 AI agent 集成

**优点：**
- Rust 实现，性能好
- 全本地推理，隐私安全
- MCP Server 对 AI agent 集成极其友好
- 现代化架构

**缺点：**
- 文档较少（主要在 koharu.rs 网站）
- Rust 生态，二次开发门槛高
- 相对较新（2025-04 创建）

---

### Tier 2：全流程方案（⭐1000-3000）

#### 4. ogkalu2/comic-translate ⭐2682
| 项目 | 详情 |
|------|------|
| **URL** | https://github.com/ogkalu2/comic-translate |
| **星标** | 2682 |
| **最后更新** | 2026-05-05（活跃） |
| **许可证** | Apache-2.0 |

**核心功能：** AI 漫画翻译应用，支持多语言多格式

**技术栈：**
- **文本检测：** RT-DETR-v2（自训练，11k 张漫画训练）
- **OCR：** manga-ocr (日文) + Pororo (韩文) + PPOCRv5 (其他) + Gemini/Azure 可选
- **擦除：** LaMa (动漫/漫画微调) + AOT-GAN
- **翻译：** GPT-4.1、Claude-4.5、Gemini-2.5（LLM 驱动）
- **GUI：** PySide6
- **格式支持：** Images, PDF, EPUB, CBR, CBZ

**CLI 能力：❌ 主要是 GUI 应用**
- 没有原生 CLI 模式
- 可以通过 Python API 调用底层模块

**优点：**
- Apache-2.0 许可证（商业友好）
- 多语言支持最好（10+ 种源语言）
- 使用 SOTA LLM 做翻译，翻译质量高
- 支持给 LLM 提供图像上下文
- 格式支持最全

**缺点：**
- 没有 CLI 模式
- 翻译依赖付费 API（GPT-4.1 等）
- 110 个 open issues

---

#### 5. kha-white/manga-ocr ⭐2639
| 项目 | 详情 |
|------|------|
| **URL** | https://github.com/kha-white/manga-ocr |
| **星标** | 2639 |
| **最后更新** | 2026-05-05（活跃） |
| **许可证** | Apache-2.0 |

**核心功能：** 专注于日文漫画的 OCR，不是全流程方案但是关键组件

**技术栈：** 基于 Vision Transformer 的 OCR 模型，专为日文漫画优化

**CLI 能力：✅ 可作为 Python 包调用**

**说明：** 这是 OCR 组件而非全流程方案，但它是几乎所有其他项目（manga-image-translator、BallonsTranslator、comic-translate）的核心 OCR 依赖。

---

#### 6. hgmzhn/manga-translator-ui ⭐1519
| 项目 | 详情 |
|------|------|
| **URL** | https://github.com/hgmzhn/manga-translator-ui |
| **星标** | 1519 |
| **最后更新** | 2026-05-05（活跃） |
| **许可证** | GPL-3.0 |

**核心功能：** 基于 manga-image-translator 的 UI 封装，内置 5 种翻译引擎

**说明：** 这是 manga-image-translator 的前端 UI 封装，核心能力来自底层项目。

---

### Tier 3：辅助工具

#### 7. dmMaze/comic-text-detector ⭐340
漫画/漫画文本检测模型，manga-image-translator 的检测组件之一。

#### 8. jtl1207/comic-translation ⭐649
基于深度学习的漫画翻译辅助工具，包含翻译、朗读、图像去字、自动嵌字。使用 PaddleOCR。CLI 能力有限。

#### 9. KUR-creative/SickZil-Machine ⭐1521
较早期的漫画翻译辅助工具，侧重于文字擦除。

#### 10. alicewish/MomoTranslator ⭐233
纯 OpenCV 的漫画翻译工具，不依赖深度学习，适合简单场景。

---

## 三、Agent 集成方案推荐

### 🥇 首选：manga-image-translator

**理由：**
1. 原生 CLI 支持，命令简洁
2. 原生 REST API，可直接 HTTP 调用
3. Docker 镜像可一键部署
4. 翻译引擎最丰富（可选离线/在线）
5. 配置文件驱动，参数化能力强

**Agent 调用示例：**
```bash
# CLI 调用
python -m manga_translator local -i input.png -l CHS --translator google

# API 调用
curl -X POST http://localhost:8001/translate -F "image=@input.png" -F "target=CHS"
```

### 🥈 备选：koharu

**理由：**
- MCP Server 原生支持 AI agent 协议
- HTTP API 可用
- 全本地推理，无需 API key

### ⚠️ 不推荐作为 Agent CLI 的项目
- **BallonsTranslator**：主要是 GUI，headless 模式不够稳定
- **comic-translate**：没有 CLI 模式，依赖 GUI

---

## 四、技术栈汇总

| 组件 | 主流方案 | 备注 |
|------|---------|------|
| **文本检测** | CRAFT, comic-text-detector (dmMaze), RT-DETR-v2 | RT-DETR 是最新的 SOTA |
| **OCR** | manga-ocr (日文), PaddleOCR (中文), Pororo (韩文) | manga-ocr 是事实标准 |
| **文字擦除** | LaMa Large, AOT-GAN | LaMa 效果更好 |
| **翻译** | GPT-4/DeepSeek/Gemini (在线), NLLB/Qwen2 (离线) | LLM 翻译质量远超传统 MT |
| **嵌字** | 各项目自研渲染引擎 | 质量参差不齐，是最大短板 |

---

## 五、嵌字质量评估

| 场景 | 效果 | 说明 |
|------|------|------|
| 日漫竖排文字泡 | ⭐⭐⭐⭐ | 效果较好，成熟场景 |
| 日漫横排文字泡 | ⭐⭐⭐ | 基本可用，偶有排版问题 |
| 中文条漫 | ⭐⭐⭐ | 简单场景 OK |
| 西式漫画 (英文) | ⭐⭐ | 文本布局不如日漫优化 |
| 无泡文字/特效字 | ⭐⭐ | 检测和擦除都有难度 |
| 复杂背景+密集文字 | ⭐⭐ | 擦除痕迹明显 |

**核心问题：** 嵌字效果受制于文字擦除质量。擦除不干净会导致最终图片有明显"补丁"感。

---

## 六、总结

| 问题 | 回答 |
|------|------|
| 有无全流程方案？ | **有**，manga-image-translator、BallonsTranslator、koharu、comic-translate 都是成熟方案 |
| 嵌字质量？ | **中等偏上**，简单日漫场景可用，复杂场景需人工调整 |
| 能否包装为 CLI？ | **完全可以**，manga-image-translator 原生 CLI + API，koharu 有 MCP Server |
| Agent 集成建议？ | 用 `manga-image-translator` 的 Docker + API 模式，或 `koharu` 的 MCP Server |
