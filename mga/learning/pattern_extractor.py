"""Stage L3 — Pattern extraction: consolidate per-page data into unified profiles."""

from __future__ import annotations

import json
import logging
from typing import Any

from .models import AlignedPageData, LearningResult

logger = logging.getLogger(__name__)


_EXTRACTION_PROMPT = """\
你是一位漫画翻译模式分析专家。你收到了从多页漫画中提取的翻译数据。
请基于这些数据，综合分析并提取以下内容：

## A. 角色档案 (characters)
对每个识别到的角色，生成统一档案：
- character_id: 基于日文名生成的ID（如 "taro" 对应 "太郎"）
- name_jp: 日文名
- name_zh: 中文名
- archetype: 角色原型（如"热血少年"、"傲娇"等）
- speech_patterns: 语言模式映射 {"自称": "我", "敬语": "不使用", "口癖": "..."}
- catchphrases: 口头禅列表
- tone_spectrum: 语气范围 {"日常": "轻松", "战斗": "热血"}
- translation_notes: 翻译注意事项

## B. 术语表 (terms)
汇总所有出现的术语：
- term_id: 基于日文词生成的ID
- term_jp: 日文原词
- term_zh: 中文译词
- context: 使用语境
- cultural_weight: "high"/"medium"/"low" — 文化重要性
- strategy: 翻译策略（直译/意译/音译/注释）
- frequency: 出现次数

## C. 风格指南 (style_guide)
分析整体翻译风格：
- literal_vs_free: 直译/意译偏好 (0-1, 0=纯直译, 1=纯意译)
- honorific_handling: 敬语处理方式
- punctuation_style: 标点习惯
- dialog_style: 对话风格
- narrative_style: 叙述风格
- key_decisions: 关键翻译决策列表

## D. 角色关系图 (character_graph)
分析角色间的互动模式：
- nodes: [{"id": "char_id", "label": "name"}]
- edges: [{"source": "char_id", "target": "char_id", "relationship": "描述", "formality": "casual/formal/polite"}]

只返回 JSON，格式如下：
{
  "characters": [...],
  "terms": [...],
  "style_guide": {...},
  "character_graph": {"nodes": [...], "edges": [...]}
}"""

_SCHEMA = {
    "type": "object",
    "properties": {
        "characters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "character_id": {"type": "string"},
                    "name_jp": {"type": "string"},
                    "name_zh": {"type": "string"},
                    "archetype": {"type": "string"},
                    "speech_patterns": {"type": "object"},
                    "catchphrases": {"type": "array", "items": {"type": "string"}},
                    "tone_spectrum": {"type": "object"},
                    "translation_notes": {"type": "object"},
                },
                "required": ["character_id", "name_jp", "name_zh"],
            },
        },
        "terms": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "term_id": {"type": "string"},
                    "term_jp": {"type": "string"},
                    "term_zh": {"type": "string"},
                    "context": {"type": "string"},
                    "cultural_weight": {"type": "string"},
                    "strategy": {"type": "string"},
                    "frequency": {"type": "integer"},
                },
                "required": ["term_id", "term_jp", "term_zh"],
            },
        },
        "style_guide": {
            "type": "object",
            "properties": {
                "literal_vs_free": {"type": "number"},
                "honorific_handling": {"type": "string"},
                "punctuation_style": {"type": "string"},
                "dialog_style": {"type": "string"},
                "narrative_style": {"type": "string"},
                "key_decisions": {"type": "array", "items": {"type": "string"}},
            },
        },
        "character_graph": {
            "type": "object",
            "properties": {
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "label": {"type": "string"},
                        },
                    },
                },
                "edges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "target": {"type": "string"},
                            "relationship": {"type": "string"},
                            "formality": {"type": "string"},
                        },
                    },
                },
            },
        },
    },
    "required": ["characters", "terms", "style_guide"],
}


def extract_patterns(
    provider: Any,
    aligned_pages: list[AlignedPageData],
) -> LearningResult:
    """Extract consolidated patterns from all aligned page data.

    Sends aggregated page data to LLM for holistic analysis.
    Falls back to heuristic aggregation if LLM fails.
    """
    if not aligned_pages:
        return LearningResult()

    # Build aggregated context from all pages
    aggregated = _aggregate_pages(aligned_pages)

    messages = [{"role": "user", "content": f"{_EXTRACTION_PROMPT}\n\n## 已提取的页面数据\n{json.dumps(aggregated, ensure_ascii=False, indent=2)}"}]

    try:
        raw = provider.chat_structured(messages=messages, schema=_SCHEMA)
        return LearningResult(
            characters=raw.get("characters", []),
            terms=raw.get("terms", []),
            style_guide=raw.get("style_guide", {}),
            character_graph=raw.get("character_graph", {"nodes": [], "edges": []}),
            pages_processed=len(aligned_pages),
        )
    except Exception as e:
        logger.warning("LLM extraction failed, falling back to heuristic: %s", e)
        return _heuristic_extract(aligned_pages)


def _aggregate_pages(pages: list[AlignedPageData]) -> dict:
    """Aggregate page data into a summary for the LLM."""
    all_characters: dict[str, dict] = {}
    all_terms: dict[str, dict] = {}
    speech_samples: dict[str, list[str]] = {}
    style_notes: list[str] = []

    for page in pages:
        for char in page.characters:
            key = char.get("name_jp", "")
            if not key:
                continue
            if key not in all_characters:
                all_characters[key] = {**char, "pages_seen": []}
            all_characters[key]["pages_seen"].append(page.page_id)
            # Merge speech_style
            existing_style = all_characters[key].get("speech_style", "")
            new_style = char.get("speech_style", "")
            if new_style and new_style not in existing_style:
                all_characters[key]["speech_style"] = f"{existing_style}; {new_style}".strip("; ")

        for term in page.terminology:
            key = term.get("term_jp", "")
            if not key:
                continue
            if key not in all_terms:
                all_terms[key] = {**term, "frequency": 0}
            all_terms[key]["frequency"] = all_terms[key].get("frequency", 0) + 1

        # Collect speech pattern samples
        for char_name, patterns in page.speech_patterns.items():
            if char_name not in speech_samples:
                speech_samples[char_name] = []
            if isinstance(patterns, dict):
                for k, v in patterns.items():
                    sample = f"{k}: {v}"
                    if sample not in speech_samples[char_name]:
                        speech_samples[char_name].append(sample)
            elif isinstance(patterns, str) and patterns not in speech_samples[char_name]:
                speech_samples[char_name].append(patterns)

        if page.style_notes:
            style_notes.append(page.style_notes)

    return {
        "characters": list(all_characters.values()),
        "terms": list(all_terms.values()),
        "speech_samples": speech_samples,
        "style_notes": style_notes,
        "total_pages": len(pages),
    }


def _heuristic_extract(pages: list[AlignedPageData]) -> LearningResult:
    """Fallback heuristic extraction when LLM is unavailable."""
    character_map: dict[str, dict] = {}
    term_map: dict[str, dict] = {}
    style_notes: list[str] = []

    for page in pages:
        for char in page.characters:
            name_jp = char.get("name_jp", "")
            if not name_jp:
                continue
            if name_jp not in character_map:
                character_map[name_jp] = {
                    "character_id": name_jp.lower().replace(" ", "_"),
                    "name_jp": name_jp,
                    "name_zh": char.get("name_zh", ""),
                    "archetype": "",
                    "speech_patterns": {},
                    "catchphrases": [],
                    "tone_spectrum": {},
                    "translation_notes": {},
                }
            # Update name_zh if we got a better one
            if char.get("name_zh"):
                character_map[name_jp]["name_zh"] = char["name_zh"]

        for term in page.terminology:
            term_jp = term.get("term_jp", "")
            if not term_jp:
                continue
            if term_jp not in term_map:
                term_map[term_jp] = {
                    "term_id": term_jp.lower().replace(" ", "_"),
                    "term_jp": term_jp,
                    "term_zh": term.get("term_zh", ""),
                    "context": term.get("context", ""),
                    "cultural_weight": "medium",
                    "strategy": "",
                    "frequency": 0,
                }
            term_map[term_jp]["frequency"] = term_map[term_jp].get("frequency", 0) + 1

        if page.style_notes:
            style_notes.append(page.style_notes)

    # Deduplicate style notes
    unique_notes = list(dict.fromkeys(style_notes))

    return LearningResult(
        characters=list(character_map.values()),
        terms=list(term_map.values()),
        style_guide={
            "literal_vs_free": 0.5,
            "honorific_handling": "unknown",
            "punctuation_style": "unknown",
            "dialog_style": "unknown",
            "narrative_style": "unknown",
            "key_decisions": [],
            "raw_notes": unique_notes,
        },
        character_graph={"nodes": [], "edges": []},
        pages_processed=len(pages),
    )
