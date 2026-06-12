"""Unified prompt builder for translation pipeline - token-optimized.

Design principles:
1. Single source of truth for all prompt templates
2. Lazy composition - only include sections when needed
3. Token budgeting - limit context size
4. Reusable sections via composition
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


# ── Constants ─────────────────────────────────────────────────────────────────

MAX_TOKENS_PER_SECTION = 500
DEFAULT_TARGET_LANG = "zh-CN"

# Shared base rules to avoid duplication
_BASE_RULES = (
    "- 所有文字翻译为中文，画面不得出现日文\n"
    "- 片假名外来语翻译为中文，footnotes 注明原文"
)

TRANSLATION_RULES = (
    "## 翻译规则\n"
    f"{_BASE_RULES}\n"
    "- 人名按中文习惯翻译，不写入 footnotes\n"
    "- 拟声词翻译为中文拟声词"
)

SEMANTIC_RULES = (
    "## 语义层规则\n"
    f"{_BASE_RULES}\n"
    "- 只翻译原文意思、事实、术语、拟声词和脚注，不做人格化\n"
    "## 脚注识别规则\n"
    "- 片假名外来语（カタカナ）：翻译为中文，添加 footnotes ['type': 'loanword']\n"
    "- 作者造词/虚构术语：保留原词感，添加 footnotes ['type': 'coined', 'explanation': '造词说明']\n"
    "- 文化特有词汇（如 highball、障子、お盆）：翻译并添加 footnotes ['type': 'cultural', 'explanation': '文化背景说明']\n"
    "- 拟声词/音效：翻译为中文，添加 footnotes ['type': 'sfx']\n"
    "- 虚构设定词（魔法、スキル等）：添加 footnotes ['type': 'fictional', 'explanation': '设定说明']\n"
    "- footnotes.translation 填写正文中使用的翻译（见正文/具体翻译均可）\n"
    "- footnotes.explanation 填写详细解释（文化背景、造词来源、含义等）\n"
)

PERSONA_RULES = (
    "## 人格层规则\n"
    "- 只允许调整语气、句式、句尾、节奏、敬语层级和口癖\n"
    "- 不得改变事实、指代、事件逻辑、专名术语\n"
    "- 最终文本必须适合直接嵌字"
)

FORMALITY_MAP = {
    "intimate": "亲密",
    "casual": "随意",
    "polite": "礼貌",
    "formal": "正式",
}

JSON_SCHEMA_TRANSLATION = "{'text':'翻译','footnotes':[],'rationale':''}"
JSON_SCHEMA_SEMANTIC = "{'text':'语义','speech_act':'','emotion':'','must_preserve':[],'footnotes':[{'original':'原文','translation':'译文','type':'loanword|coined|cultural|fictional|sfx','explanation':'详细解释（可选）'}],'rationale':'','confidence':0.8}"
JSON_SCHEMA_PERSONA = "{'text':'人格','persona_moves':[],'rationale':'','confidence':0.8}"


# ── Section Builders ───────────────────────────────────────────────────────────

@dataclass
class PromptSection:
    """Represents a single prompt section with token budget."""
    title: str
    lines: list[str] = field(default_factory=list)
    max_tokens: int = MAX_TOKENS_PER_SECTION

    def render(self) -> str:
        """Render section as string, respecting token budget."""
        if not self.lines:
            return ""
        content = "\n".join(self.lines)
        if len(content) > self.max_tokens:
            content = content[:self.max_tokens] + "..."
        return f"{self.title}\n{content}"


@dataclass
class PromptBuilder:
    """Unified prompt builder with token optimization."""

    target_lang: str = DEFAULT_TARGET_LANG
    sections: list[PromptSection] = field(default_factory=list)

    def add_section(self, title: str, lines: list[str]) -> "PromptBuilder":
        """Add a section to the prompt."""
        self.sections.append(PromptSection(title=title, lines=lines))
        return self

    def add_rule_block(self, rules: str) -> "PromptBuilder":
        """Add a rule block as a single section."""
        if rules:
            self.add_section("", [rules])
        return self

    def add_if(
        self,
        condition: Any,
        title: str,
        lines: list[str],
    ) -> "PromptBuilder":
        """Conditionally add a section."""
        if condition:
            self.add_section(title, lines)
        return self

    def add_profile(self, memory_ctx: dict) -> "PromptBuilder":
        """Add character profile section from memory context."""
        if not memory_ctx:
            return self

        lines = []
        if memory_ctx.get("name_jp") or memory_ctx.get("name_zh"):
            name_line = f"- 名字：{memory_ctx.get('name_jp', '')}"
            if memory_ctx.get("name_zh"):
                name_line += f" → {memory_ctx['name_zh']}"
            lines.append(name_line)
        if memory_ctx.get("archetype"):
            lines.append(f"- 原型：{memory_ctx['archetype']}")
        if memory_ctx.get("speech_patterns"):
            patterns = "; ".join(f"{k}={v}" for k, v in memory_ctx["speech_patterns"].items())
            lines.append(f"- 语言模式：{patterns}")
        if memory_ctx.get("catchphrases"):
            lines.append(f"- 口头禅：{', '.join(memory_ctx['catchphrases'])}")
        if memory_ctx.get("tone_spectrum"):
            tones = "; ".join(f"{k}={v}" for k, v in memory_ctx["tone_spectrum"].items())
            lines.append(f"- 语气：{tones}")
        if memory_ctx.get("translation_notes"):
            notes = "; ".join(f"{k}={v}" for k, v in memory_ctx["translation_notes"].items())
            lines.append(f"- 翻译注意：{notes}")

        if lines:
            self.add_section("## 角色档案", lines)
        return self

    def add_relationship(self, relationship_ctx: str) -> "PromptBuilder":
        """Add relationship context section."""
        if relationship_ctx:
            self.add_section("", [relationship_ctx])
        return self

    def add_vision(self, vision_ctx: dict) -> "PromptBuilder":
        """Add vision context section."""
        if not vision_ctx:
            return self

        lines = []
        if vision_ctx.get("provisional_speaker"):
            lines.append(f"- 临时说话人：{vision_ctx['provisional_speaker']}（仅供语气参考）")
        if vision_ctx.get("voice_hint"):
            lines.append(f"- 语言风格：{vision_ctx['voice_hint']}")
        if vision_ctx.get("box_type"):
            lines.append(f"- 文本框类型：{vision_ctx['box_type']}")
        if vision_ctx.get("page_voice_hints"):
            lines.append(f"- 页级语言观察：{'; '.join(vision_ctx['page_voice_hints'])}")

        if lines:
            self.add_section("## Vision 补充提示", lines)
        return self

    def add_cultural(self, cultural_ctx: dict) -> "PromptBuilder":
        """Add cultural context section."""
        ctx = cultural_ctx.get("translation_context", "")
        if ctx:
            self.add_section("", [ctx])
        return self

    def add_scene(
        self,
        scene_summary: str = "",
        scene_context: dict | None = None,
    ) -> "PromptBuilder":
        """Add scene context section."""
        if scene_summary:
            self.add_section("## Page Summary", [scene_summary])
        if scene_context:
            self._add_scene_context(scene_context)
        return self

    def _add_scene_context(self, scene_context: dict) -> None:
        """Format and add scene memory context."""
        scalar_fields = [
            ("scene_id", "scene_id"),
            ("mood", "mood"),
            ("scene_description", "scene_description"),
            ("narrative_summary", "narrative_summary"),
            ("future_impact", "future_impact"),
        ]
        lines = []
        for key, label in scalar_fields:
            value = scene_context.get(key)
            if value:
                lines.append(f"- {label}: {value}")

        list_fields = [
            ("relationship_changes", "relationship_changes"),
            ("key_dialogue", "key_dialogue"),
        ]
        for key, label in list_fields:
            values = scene_context.get(key) or []
            if values:
                lines.append(f"- {label}:")
                lines.extend(f"  - {item}" for item in values)

        characters = scene_context.get("characters") or []
        if characters:
            lines.append("- characters:")
            for character in characters:
                if not isinstance(character, dict):
                    lines.append(f"  - {character}")
                    continue
                bits = [
                    str(character.get("character_id", "")),
                    str(character.get("name_jp", "")),
                    str(character.get("name_zh", "")),
                ]
                label = " / ".join(bit for bit in bits if bit)
                if label:
                    lines.append(f"  - {label}")

        if lines:
            self.add_section("## Scene Memory", lines)

    def add_source(self, source_text: str) -> "PromptBuilder":
        """Add source text section."""
        self.add_section("", [f"Source: {source_text}"])
        return self

    def add_semantic(self, semantic: Any) -> "PromptBuilder":
        """Add semantic translation as input."""
        if hasattr(semantic, 'model_dump'):
            data = semantic.model_dump()
        else:
            data = semantic
        self.add_section("## Semantic Translation", [json.dumps(data, ensure_ascii=False)])
        return self

    def render(self) -> str:
        """Render all sections into final prompt."""
        return "\n".join(
            section.render()
            for section in self.sections
            if section.render()
        )


# ── Convenience Functions ──────────────────────────────────────────────────────

def build_translation_prompt(
    source_text: str,
    memory_ctx: dict,
    cultural_ctx: dict,
    target_lang: str = DEFAULT_TARGET_LANG,
    relationship_ctx: str = "",
    vision_ctx: dict | None = None,
) -> str:
    """Build translation prompt with character/cultural context injection.

    Optimized single-prompt version for simple translation needs.
    """
    builder = (
        PromptBuilder(target_lang=target_lang)
        .add_section(
            "",
            [f"Translate manga dialogue to {target_lang}."],
        )
        .add_rule_block(TRANSLATION_RULES)
        .add_profile(memory_ctx)
        .add_relationship(relationship_ctx)
        .add_vision(vision_ctx or {})
        .add_cultural(cultural_ctx)
        .add_source(source_text)
        .add_section("", [f"Return JSON: {JSON_SCHEMA_TRANSLATION}"])
    )
    return builder.render()


def build_semantic_prompt(
    source_text: str,
    cultural_ctx: dict,
    target_lang: str = DEFAULT_TARGET_LANG,
    vision_ctx: dict | None = None,
    translation_memory: list[dict[str, Any]] | None = None,
) -> str:
    """Build semantic translation prompt - meaning-faithful draft."""
    from mga.memory import MemoryRetrieval

    builder = (
        PromptBuilder(target_lang=target_lang)
        .add_section("## Semantic Translation", [f"Translate manga text to {target_lang} as meaning-faithful semantic draft."])
        .add_rule_block(SEMANTIC_RULES)
    )

    if vision_ctx and vision_ctx.get("box_type"):
        builder.add_section("", [f"- 文本框类型：{vision_ctx['box_type']}"])

    if cultural_ctx.get("translation_context"):
        builder.add_section("## 文化与术语约束", [cultural_ctx["translation_context"]])

    memory_block = MemoryRetrieval.format_translation_memory_context(translation_memory or [])
    if memory_block:
        builder.add_section("", [memory_block])

    builder.add_source(source_text)
    builder.add_section(
        "",
        [f"Return JSON: {JSON_SCHEMA_SEMANTIC}"],
    )
    return builder.render()


def build_persona_prompt(
    source_text: str,
    semantic: Any,
    memory_ctx: dict,
    target_lang: str = DEFAULT_TARGET_LANG,
    relationship_ctx: str = "",
    vision_ctx: dict | None = None,
    listener_id: str | None = None,
    scene_summary: str = "",
    scene_context: dict | None = None,
    relationship_data: dict | None = None,
) -> str:
    """Build persona render prompt - final dialogue rendering."""
    builder = (
        PromptBuilder(target_lang=target_lang)
        .add_section("## Persona Rendering", ["Render semantic translation as final manga dialogue in Chinese."])
        .add_rule_block(PERSONA_RULES)
        .add_source(source_text)
        .add_semantic(semantic)
        .add_profile(memory_ctx)
        .add_relationship(relationship_ctx)
    )

    # Relationship speech rules
    if listener_id:
        rule_block = format_relationship_speech_rule(memory_ctx, listener_id, relationship_data)
        if rule_block:
            builder.add_section("", [rule_block])

    builder.add_scene(scene_summary, scene_context)
    builder.add_vision(vision_ctx or {})
    builder.add_section("", [f"Return JSON: {JSON_SCHEMA_PERSONA}"])

    return builder.render()


# ── Relationship Helpers ───────────────────────────────────────────────────────

def relationship_speech_rule(
    memory_ctx: dict,
    listener_id: str | None,
) -> tuple[str, dict[str, Any]] | None:
    """Extract relationship speech rule for a listener."""
    if not listener_id:
        return None
    rules = memory_ctx.get("relationship_speech", {})
    if not isinstance(rules, dict):
        return None
    rule = rules.get(listener_id)
    if isinstance(rule, dict):
        return listener_id, rule
    for key, value in rules.items():
        if isinstance(value, dict) and str(value.get("listener_id", "")) == listener_id:
            return str(key), value
    return None


def format_relationship_speech_rule(
    memory_ctx: dict,
    listener_id: str | None,
    relationship_data: dict | None = None,
) -> str:
    """Format relationship speech rule as prompt section."""
    selected = relationship_speech_rule(memory_ctx, listener_id)

    if selected is None and relationship_data:
        rel = relationship_data.get("relationship", "")
        form = relationship_data.get("formality", "casual")
        hon = relationship_data.get("honorific", "")
        if rel or hon:
            formality_zh = FORMALITY_MAP.get(form, form)
            parts = [
                "## Relationship-specific speech rules",
                f"- listener_id: {listener_id}",
                f"- relationship: {rel}",
                f"- formality: {formality_zh}",
            ]
            if hon:
                parts.append(f"- honorific: {hon}")
            return "\n".join(parts)

    if selected is None:
        return ""

    label, rule = selected
    parts = [
        "## Relationship-specific speech rules",
        f"- listener_id: {listener_id}",
        f"- rule: {label}",
    ]
    for key, value in rule.items():
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        parts.append(f"- {key}: {value}")
    return "\n".join(parts)


def format_scene_memory(scene_context: dict[str, Any]) -> str:
    """Format scene memory context as prompt section."""
    builder = PromptBuilder()
    builder._add_scene_context(scene_context)
    sections = [s for s in builder.sections if s.render()]
    return "\n".join(s.render() for s in sections)


# ── Backward Compatibility ──────────────────────────────────────────────────────

# Keep old function names as aliases for existing code
_build_translation_prompt = build_translation_prompt
_build_semantic_translation_prompt = build_semantic_prompt
_build_persona_render_prompt = build_persona_prompt
_relationship_speech_rule = relationship_speech_rule
_format_relationship_speech_rule = format_relationship_speech_rule
_format_scene_memory = format_scene_memory

__all__ = [
    # Classes
    "PromptBuilder",
    "PromptSection",
    # New API
    "build_translation_prompt",
    "build_semantic_prompt",
    "build_persona_prompt",
    "relationship_speech_rule",
    "format_relationship_speech_rule",
    "format_scene_memory",
    # Backward compatibility
    "_build_translation_prompt",
    "_build_semantic_translation_prompt",
    "_build_persona_render_prompt",
    "_relationship_speech_rule",
    "_format_relationship_speech_rule",
    "_format_scene_memory",
]