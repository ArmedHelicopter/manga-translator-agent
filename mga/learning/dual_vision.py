"""Stage L2 — Dual vision: extract structured data from original+translated page pairs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .models import AlignedPageData, PagePair

logger = logging.getLogger(__name__)


_VISION_PROMPT = """\
你是一位漫画翻译分析师。你会收到一对漫画页面——原图（日文）和已翻译的版本（中文）。

请分析这对页面并提取以下信息，以 JSON 格式返回：

1. **source_text**: 每个气泡中的日文原文，按阅读顺序排列，用换行分隔
2. **translated_text**: 每个气泡中的中文译文，按阅读顺序排列，用换行分隔
3. **characters**: 识别出的角色列表，每个角色包含：
   - name_jp: 日文名
   - name_zh: 中文名
   - appearance: 外貌描述
   - speech_style: 说话风格
4. **terminology**: 提取的术语列表，每个术语包含：
   - term_jp: 日文原词
   - term_zh: 中文译词
   - context: 使用语境
5. **speech_patterns**: 每个角色的语言模式（自称、口癖、敬语使用等）
6. **style_notes**: 整体翻译风格描述（直译/意译偏好、语气处理等）

只返回 JSON，不要包含其他文字。"""

_NOVEL_PROMPT = """\
你是一位小说翻译分析师。你会收到一段日文原文和对应的中文翻译。

请分析这对文本并提取以下信息，以 JSON 格式返回：

1. **source_text**: 日文原文
2. **translated_text**: 中文译文
3. **characters**: 文中出现的角色，每个角色包含：
   - name_jp: 日文名
   - name_zh: 中文名
   - speech_style: 说话风格
4. **terminology**: 专有名词和术语，每个包含：
   - term_jp: 日文原词
   - term_zh: 中文译词
   - context: 使用语境
5. **speech_patterns**: 角色语言模式
6. **style_notes**: 翻译风格描述

只返回 JSON，不要包含其他文字。"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "source_text": {"type": "string"},
        "translated_text": {"type": "string"},
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name_jp": {"type": "string"},
                    "name_zh": {"type": "string"},
                    "appearance": {"type": "string"},
                    "speech_style": {"type": "string"},
                },
                "required": ["name_jp", "name_zh"],
            },
        },
        "terminology": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term_jp": {"type": "string"},
                    "term_zh": {"type": "string"},
                    "context": {"type": "string"},
                },
                "required": ["term_jp", "term_zh"],
            },
        },
        "speech_patterns": {"type": "object"},
        "style_notes": {"type": "string"},
    },
    "required": ["source_text", "translated_text", "characters", "terminology", "style_notes"],
}


def analyze_manga_pair(
    provider: Any,
    pair: PagePair,
) -> AlignedPageData | None:
    """Analyze a manga page pair using vision provider.

    Reads both images, sends to LLM with vision(), returns structured data.
    """
    orig_path = Path(pair.original_path)
    trans_path = Path(pair.translated_path)

    if not orig_path.exists() or not trans_path.exists():
        logger.warning("Missing image files for pair %s", pair.page_id)
        return None

    orig_bytes = orig_path.read_bytes()
    trans_bytes = trans_path.read_bytes()

    messages = [{"role": "user", "content": _VISION_PROMPT}]

    try:
        raw = provider.vision_structured(
            messages=messages,
            images=[orig_bytes, trans_bytes],
            schema=_SCHEMA,
        )
    except Exception:
        logger.warning("vision_structured failed for %s, falling back to chat", pair.page_id)
        try:
            raw_text = provider.vision(
                messages=messages,
                images=[orig_bytes, trans_bytes],
            )
            raw = _parse_json_response(raw_text)
        except Exception as e:
            logger.error("Failed to analyze pair %s: %s", pair.page_id, e)
            return None

    return AlignedPageData(
        page_id=pair.page_id,
        source_text=raw.get("source_text", ""),
        translated_text=raw.get("translated_text", ""),
        characters=raw.get("characters", []),
        terminology=raw.get("terminology", []),
        speech_patterns=raw.get("speech_patterns", {}),
        style_notes=raw.get("style_notes", ""),
    )


def analyze_novel_pair(
    provider: Any,
    pair: PagePair,
) -> AlignedPageData | None:
    """Analyze a novel text pair using text-only chat provider."""
    orig_path = Path(pair.original_path)
    trans_path = Path(pair.translated_path)

    if not orig_path.exists() or not trans_path.exists():
        logger.warning("Missing text files for pair %s", pair.page_id)
        return None

    source_text = orig_path.read_text(encoding="utf-8")
    translated_text = trans_path.read_text(encoding="utf-8")

    content = f"## 日文原文\n{source_text}\n\n## 中文翻译\n{translated_text}"
    messages = [{"role": "user", "content": f"{_NOVEL_PROMPT}\n\n{content}"}]

    try:
        raw = provider.chat_structured(
            messages=messages,
            schema=_SCHEMA,
        )
    except Exception:
        logger.warning("chat_structured failed for %s, falling back to chat", pair.page_id)
        try:
            raw_text = provider.chat(messages=messages)
            raw = _parse_json_response(raw_text)
        except Exception as e:
            logger.error("Failed to analyze pair %s: %s", pair.page_id, e)
            return None

    return AlignedPageData(
        page_id=pair.page_id,
        source_text=raw.get("source_text", source_text),
        translated_text=raw.get("translated_text", translated_text),
        characters=raw.get("characters", []),
        terminology=raw.get("terminology", []),
        speech_patterns=raw.get("speech_patterns", {}),
        style_notes=raw.get("style_notes", ""),
    )


def analyze_pairs(
    provider: Any,
    pairs: list[PagePair],
    mode: str = "auto",
) -> list[AlignedPageData]:
    """Analyze all page pairs. Mode: 'manga', 'novel', or 'auto' (detect from extensions)."""
    from .aligner import _IMAGE_EXTS, _TEXT_EXTS

    results: list[AlignedPageData] = []
    for pair in pairs:
        ext = Path(pair.original_path).suffix.lower()

        if mode == "manga" or (mode == "auto" and ext in _IMAGE_EXTS):
            result = analyze_manga_pair(provider, pair)
        elif mode == "novel" or (mode == "auto" and ext in _TEXT_EXTS):
            result = analyze_novel_pair(provider, pair)
        else:
            logger.warning("Unknown file type for %s, skipping", pair.page_id)
            continue

        if result is not None:
            results.append(result)

    logger.info("Analyzed %d/%d page pairs", len(results), len(pairs))
    return results


def _parse_json_response(text: str) -> dict:
    """Extract JSON from LLM response that may contain markdown code fences."""
    text = text.strip()
    if text.startswith("```"):
        # Remove markdown code fences
        lines = text.split("\n")
        # Find opening and closing fences
        start = 1  # skip first line (```json or ```)
        end = len(lines) - 1
        for i, line in enumerate(lines):
            if i > 0 and line.strip().startswith("```"):
                end = i
                break
        text = "\n".join(lines[start:end])
    return json.loads(text)
