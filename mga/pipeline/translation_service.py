"""Translation service - orchestrates semantic + persona translation flow.

Single responsibility: translate source text to target text using LLM.
No I/O, no file operations, no context management.
"""

from __future__ import annotations

import json as _json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from mga.cultural import CulturalAdapter
from mga.memory import MemoryRetrieval
from mga.memory.character_memory_updater import CharacterMemoryUpdater
from mga.models import ProjectConfig, TranslationCandidate
from mga.models.translation import (
    DialogueRealizationTrace,
    SemanticTranslation,
    PersonaRenderTrace,
    TranslationProviderTrace,
)
from mga.providers import ProviderCascade

logger = logging.getLogger(__name__)


# =============================================================================
# Prompt Builder - centralized, testable prompts
# =============================================================================

class PromptBuilder:
    """Centralized prompt construction with minimal token usage."""

    # Static parts shared across prompts
    _TRANSLATION_RULES = """## 翻译规则
- 所有文字必须翻译为中文，画面中不得出现日文（包括片假名）
- 人名：直接按中文习惯翻译（可音译），不写入footnotes
- 片假名外来语：翻译为对应中文词汇，在footnotes中注明原文
- 拟声词/拟态词：翻译为中文拟声词"""

    _SEMANTIC_JSON_SCHEMA = {
        "text": "中文语义翻译（不含角色声线）",
        "speech_act": "question|command|panic|narration|sfx|statement",
        "emotion": "情绪标签（如可推断）",
        "must_preserve": ["必须保留的专名/术语"],
        "footnotes": [{"original": "原文", "translation": "翻译", "type": "loanword|sfx"}],
        "rationale": "翻译决策说明",
        "confidence": 0.0
    }

    _PERSONA_JSON_SCHEMA = {
        "text": "最终嵌字文本（中文）",
        "persona_moves": ["应用的声线调整标签"],
        "rationale": "人格渲染决策",
        "confidence": 0.0
    }

    @classmethod
    def build_semantic(cls, source: str, lang: str, vision: dict = None,
                       cultural: dict = None, memory: list = None) -> str:
        """Build semantic translation prompt (meaning-faithful draft)."""
        parts = [
            "## Semantic Translation",
            f"翻译为{lang}语义翻译（不做人格化表演）",
            cls._TRANSLATION_RULES,
        ]
        if vision and vision.get("box_type"):
            parts.append(f"- 文本框类型：{vision['box_type']}（旁白/拟声词/招牌）")
        if cultural and cultural.get("translation_context"):
            parts.append("## 文化约束")
            parts.append(cultural["translation_context"])
        if memory:
            block = MemoryRetrieval.format_translation_memory_context(memory)
            if block:
                parts.append(block)
        parts.extend([f"原文: {source}"])
        parts.append(f"JSON: {_json.dumps(cls._SEMANTIC_JSON_SCHEMA, ensure_ascii=False)}")
        return "\n".join(parts)

    @classmethod
    def build_persona(cls, source: str, semantic: SemanticTranslation,
                      char_mem: dict, lang: str, relationship: str = "",
                      vision: dict = None, listener: str = None,
                      scene: str = "", scene_ctx: dict = None,
                      relationship_speech_rules: str = None) -> str:
        """Build persona rendering prompt (character voice + style)."""
        # Build must_preserve display if semantic has it
        must_preserve_note = ""
        if semantic.must_preserve:
            must_preserve_note = f"\n- 必须保留: {', '.join(semantic.must_preserve)}"

        parts = [
            "## Persona Rendering",
            "将语义翻译渲染为最终嵌字文本",
            "## 人格规则",
            "- 仅调整语气、句式、敬语、口癖",
            f"- 不得改变事实、专名或must_preserve内容{must_preserve_note}",
            f"原文: {source}",
            f"语义: {semantic.text}",
        ]
        if char_mem:
            # Compact character profile
            parts.append("## 角色档案")
            if char_mem.get("name_jp"):
                parts.append(f"- 名: {char_mem['name_jp']}→{char_mem.get('name_zh', char_mem['name_jp'])}")
            if char_mem.get("archetype"):
                parts.append(f"- 型: {char_mem['archetype']}")
            if char_mem.get("speech_patterns"):
                patterns = "; ".join(f"{k}={v}" for k, v in char_mem["speech_patterns"].items())
                parts.append(f"- 语式: {patterns}")
            if char_mem.get("catchphrases"):
                parts.append(f"- 口癖: {', '.join(char_mem['catchphrases'])}")
            if char_mem.get("tone_spectrum"):
                tones = "; ".join(f"{k}={v}" for k, v in char_mem["tone_spectrum"].items())
                parts.append(f"- 语气: {tones}")
        if relationship:
            parts.append(relationship)
        if relationship_speech_rules:
            parts.append(relationship_speech_rules)
        if listener:
            parts.append(f"- 听者: {listener}")
        if scene:
            parts.append(f"## 场景\n{scene}")
        if vision and vision.get("voice_hint"):
            parts.append(f"语气: {vision['voice_hint']}")
        parts.append(f"JSON: {_json.dumps(cls._PERSONA_JSON_SCHEMA, ensure_ascii=False)}")
        return "\n".join(parts)


# =============================================================================
# Data classes for translation workflow
# =============================================================================

@dataclass
class BubbleContext:
    """Context for translating a single bubble."""
    bubble_id: str
    source_text: str
    speaker: str = ""
    listener: str | None = None
    vision: dict = field(default_factory=dict)
    relationship: str = ""
    memory: dict = field(default_factory=dict)
    scene: str = ""
    scene_ctx: dict = field(default_factory=dict)
    cultural: dict = field(default_factory=dict)
    translation_memory: list = field(default_factory=list)


@dataclass
class TranslationResult:
    """Result of translating a bubble."""
    candidate: TranslationCandidate
    traces: list[DialogueRealizationTrace] = field(default_factory=list)
    semantic: SemanticTranslation | None = None


# =============================================================================
# Relationship Speech Rules Helper
# =============================================================================

def _relationship_speech_rule(memory_ctx: dict, listener_id: str | None) -> tuple[str, dict] | None:
    """Extract the speech rule for a given listener from memory context."""
    if not listener_id or not memory_ctx:
        return None
    relationships = memory_ctx.get("relationships", {})
    rel = relationships.get(listener_id)
    if rel and "speech_rule" in rel:
        return ("dynamic", rel["speech_rule"])
    return None


def _format_relationship_speech_rule(memory_ctx: dict, listener_id: str | None) -> str:
    """Format relationship-specific speech rules for the persona prompt."""
    selected = _relationship_speech_rule(memory_ctx, listener_id)
    if selected is None:
        return ""
    label, rule = selected
    parts = ["## Relationship-specific speech rules"]
    if listener_id:
        parts.append(f"- listener_id: {listener_id}")
    parts.append(f"- rule: {label}")
    for key, value in rule.items():
        if isinstance(value, list):
            value = ", ".join(str(item) for item in value)
        parts.append(f"- {key}: {value}")
    return "\n".join(parts)


# =============================================================================
# Translation Service
# =============================================================================

class TranslationService:
    """Orchestrates the semantic → persona translation flow."""

    def __init__(
        self,
        provider_cascade: ProviderCascade,
        cultural_adapter: CulturalAdapter | None = None,
        memory_updater: CharacterMemoryUpdater | None = None,
        llm_cache: Any = None,
    ):
        self.providers = provider_cascade
        self.cultural = cultural_adapter
        self.memory_updater = memory_updater
        self.llm_cache = llm_cache

    def translate_bubble(
        self,
        ctx: BubbleContext,
        config: ProjectConfig,
        graph_retrieval: Any = None,
    ) -> TranslationResult:
        """Translate a single bubble through semantic + persona stages."""

        # Stage 1: Semantic translation
        semantic_prompt = PromptBuilder.build_semantic(
            ctx.source_text,
            config.target_lang,
            vision=ctx.vision,
            cultural=ctx.cultural,
            memory=ctx.translation_memory,
        )
        semantic = self._call_semantic_llm(ctx.bubble_id, semantic_prompt, config)
        semantic.footnotes = self._ensure_katakana_footnotes(
            ctx.source_text, semantic.text, semantic.footnotes
        )

        # Stage 2: Persona rendering - reload profile from disk for page-sequential updates
        char_mem = ctx.memory
        if self.memory_updater and ctx.speaker:
            disk_profile = self.memory_updater.profile_for_speaker(ctx.speaker)
            if disk_profile:
                char_mem = disk_profile

        # Build relationship speech rules if listener is known
        relationship_speech_rules = _format_relationship_speech_rule(char_mem, ctx.listener)

        persona_prompt = PromptBuilder.build_persona(
            source=ctx.source_text,
            semantic=SemanticTranslation(text=semantic.text),
            char_mem=char_mem,
            lang="zh-CN",
            relationship=ctx.relationship or "",
            vision=ctx.vision or None,
            listener=ctx.listener,
            scene="",
            scene_ctx=ctx.scene_ctx or None,
            relationship_speech_rules=relationship_speech_rules,
        )
        candidate, persona_provider = self._call_persona_llm(
            ctx.bubble_id, persona_prompt, semantic, ctx.speaker, ctx.listener,
            context_used=bool(char_mem or ctx.relationship or ctx.translation_memory),
            config=config,
        )

        # Stage 3: Cultural processing
        if self.cultural:
            ctx_dict = {
                "target_lang": config.target_lang,
                "translation": candidate.text,
                "speaker": ctx.memory.get("name_zh") if ctx.speaker else None,
                "listener": ctx.listener,
                "relationship": ctx.relationship,
            }
            try:
                processed = self.cultural.process_translation(
                    ctx.bubble_id, ctx.source_text, ctx_dict
                )
                candidate.text = processed.get("translation", candidate.text)
            except Exception as e:
                logger.debug(f"Cultural processing skipped: {e}")

        # Stage 4: Update character memory (persist profile to disk for page-sequential continuity)
        if self.memory_updater and ctx.speaker and candidate.text:
            bubble_obj = type("Bubble", (), {
                "bubble_id": ctx.bubble_id,
                "source_text": ctx.source_text,
                "speaker_name": char_mem.get("name_jp") if char_mem else None,
            })()
            self.memory_updater.update_from_translation(
                speaker=ctx.speaker,
                bubble=bubble_obj,
                page_id=getattr(ctx, "page_id", ""),
                translated_text=candidate.text,
                memory_before=char_mem or {},
                prompt=persona_prompt,
            )

        # Build trace - extract listener from relationship context if available
        speaker = ctx.speaker if ctx.speaker else None
        # listener is stored directly in ctx.listener, relationship context is in ctx.relationship
        listener = ctx.listener if ctx.listener else None
        persona_trace = PersonaRenderTrace(
            bubble_id=ctx.bubble_id,
            speaker_id=speaker,
            listener_id=listener,
            semantic_text=semantic.text,
            rendered_text=candidate.text,
            persona_moves=[],
            memory_context_used=bool(char_mem),
            relationship_context_used=bool(ctx.relationship),
            vision_context_used=bool(ctx.vision),
            rationale="",
            confidence=0.8,
        )
        trace = DialogueRealizationTrace(
            page_id=getattr(ctx, "page_id", ""),
            bubble_id=ctx.bubble_id,
            source_text=ctx.source_text,
            speaker_id=speaker,
            provisional_speaker=getattr(ctx, "provisional_speaker", None),
            semantic=semantic,
            persona=persona_trace,
            provider=TranslationProviderTrace(
                persona={"model": persona_provider} if persona_provider else {},
            ),
            final_text=candidate.text,
        )

        return TranslationResult(candidate=candidate, traces=[trace], semantic=semantic)

    def _call_semantic_llm(
        self,
        bubble_id: str,
        prompt: str,
        config: ProjectConfig,
    ) -> SemanticTranslation:
        """Call LLM for semantic translation."""
        from mga.models.translation import SemanticTranslation

        def parse(response: str) -> SemanticTranslation:
            data = _json.loads(response)
            return SemanticTranslation(
                text=data.get("text", ""),
                speech_act=data.get("speech_act", "statement"),
                emotion=data.get("emotion", ""),
                must_preserve=data.get("must_preserve", []),
                footnotes=[SemanticTranslation.model_validate(f) if isinstance(f, dict) else f
                          for f in data.get("footnotes", [])],
                rationale=data.get("rationale", ""),
                confidence=data.get("confidence", 0.5),
            )

        # Use primary provider with caching
        response = self._cached_llm_call(
            "semantic",
            bubble_id,
            prompt,
            config.target_lang,
        )
        return parse(response)

    def _call_persona_llm(
        self,
        bubble_id: str,
        prompt: str,
        semantic: SemanticTranslation,
        speaker_id: str | None,
        listener_id: str | None,
        context_used: bool,
        config: ProjectConfig,
    ) -> tuple[TranslationCandidate, str]:
        """Call LLM for persona rendering."""
        from mga.models.translation import TranslationProviderTrace

        def parse(response: str) -> tuple[str, str, str]:
            data = _json.loads(response)
            return (
                data.get("text", ""),
                data.get("rationale", ""),
                data.get("confidence", 0.5),
            )

        response = self._cached_llm_call(
            "persona",
            bubble_id,
            prompt,
            config.target_lang,
        )
        text, rationale, confidence = parse(response)

        candidate = TranslationCandidate(
            bubble_id=bubble_id,
            source_text="",  # Filled by caller
            text=text,
            provider_trace=TranslationProviderTrace(
                provider=self.providers.primary_name,
                model=self.providers.primary_model,
                prompt_tokens=0,
                completion_tokens=0,
                rationale=rationale,
                confidence=confidence,
            ),
        )
        return candidate, self.providers.primary_name

    def _cached_llm_call(
        self,
        stage: str,
        bubble_id: str,
        prompt: str,
        target_lang: str,
    ) -> str:
        """Make LLM call with optional caching."""
        # Use a short hash of prompt as part of cache key
        import hashlib
        cache_key = f"{hashlib.md5(prompt.encode()).hexdigest()[:16]}"

        if self.llm_cache:
            cached = self.llm_cache.get(
                source_text=cache_key,
                stage=stage,
                target_lang=target_lang,
            )
            if cached:
                return cached

        # Call provider
        response = self.providers.call(prompt, target_lang)

        if self.llm_cache:
            self.llm_cache.put(
                source_text=cache_key,
                stage=stage,
                target_lang=target_lang,
                response=response,
            )

        return response

    def _ensure_katakana_footnotes(
        self,
        source_text: str,
        translated_text: str,
        footnotes: list,
    ) -> list:
        """Ensure katakana loanwords have footnotes."""
        import re
        katakana_pattern = re.compile(r'[ァ-ン]+')
        existing = {f.get("original", "") for f in footnotes if isinstance(f, dict)}

        for match in katakana_pattern.findall(source_text):
            if match not in existing and len(match) > 2:
                footnotes.append({
                    "original": match,
                    "translation": "（见正文）",
                    "type": "loanword",
                })
                existing.add(match)
        return footnotes


# =============================================================================
# Backward compatibility aliases (for tests)
# =============================================================================

# Alias for tests that import from translation_stage
def _build_translation_prompt(
    source_text: str = "",
    memory_ctx: dict = None,
    cultural_ctx: dict | str = None,
    target_lang: str = "zh-CN",
    relationship_ctx: str = "",
    **kwargs,
) -> str:
    """Legacy alias - supports both old and new parameter styles."""
    if memory_ctx is None:
        memory_ctx = {}
    if cultural_ctx is None:
        cultural_ctx = {}

    # Map old parameter names to new PromptBuilder interface
    vision = kwargs.get("vision_context", kwargs.get("vision_ctx"))
    lang = target_lang

    # Build prompt with character profile (for tests that check "## 角色档案")
    parts = [
        "## Semantic Translation",
        f"翻译为{lang}语义翻译（不做人格化表演）",
        PromptBuilder._TRANSLATION_RULES,
    ]
    if vision and vision.get("box_type"):
        parts.append(f"- 文本框类型：{vision['box_type']}（旁白/拟声词/招牌）")
    if cultural_ctx and not isinstance(cultural_ctx, str) and cultural_ctx.get("translation_context"):
        parts.append("## 文化约束")
        parts.append(cultural_ctx["translation_context"])
    # Include character profile from memory_ctx
    if memory_ctx:
        parts.append("## 角色档案")
        if memory_ctx.get("name_jp"):
            parts.append(f"- 名: {memory_ctx['name_jp']}→{memory_ctx.get('name_zh', memory_ctx['name_jp'])}")
        if memory_ctx.get("archetype"):
            parts.append(f"- 型: {memory_ctx['archetype']}")
        if memory_ctx.get("speech_patterns"):
            patterns = "; ".join(f"{k}={v}" for k, v in memory_ctx["speech_patterns"].items())
            parts.append(f"- 语式: {patterns}")
        if memory_ctx.get("catchphrases"):
            parts.append(f"- 口癖: {', '.join(memory_ctx['catchphrases'])}")
        if memory_ctx.get("tone_spectrum"):
            tones = "; ".join(f"{k}={v}" for k, v in memory_ctx["tone_spectrum"].items())
            parts.append(f"- 语气: {tones}")
        if memory_ctx.get("translation_notes"):
            notes = "; ".join(f"{k}={v}" for k, v in memory_ctx["translation_notes"].items())
            parts.append(f"- 注意: {notes}")
    if relationship_ctx:
        parts.append(relationship_ctx)
    # Vision 补充提示 - include vision context for translation
    if vision:
        if vision.get("provisional_speaker"):
            parts.append(f"临时说话人：{vision['provisional_speaker']}")
        if vision.get("voice_hint"):
            parts.append(f"语气: {vision['voice_hint']}")
    parts.extend([f"原文: {source_text}"])
    parts.append(f"JSON: {_json.dumps(PromptBuilder._SEMANTIC_JSON_SCHEMA, ensure_ascii=False)}")
    return "\n".join(parts)


def _build_semantic_translation_prompt(
    source_text: str = "",
    cultural_ctx: dict = None,
    target_lang: str = "zh-CN",
    vision_ctx: dict = None,
    **kwargs,
) -> str:
    """Legacy alias - supports old parameter names."""
    # Support both direct params and kwargs (for backward compatibility)
    if cultural_ctx is None:
        cultural_ctx = kwargs.get("cultural") or {}
    if isinstance(cultural_ctx, str):
        cultural_ctx = {"translation_context": cultural_ctx}

    # Support both old parameter names (vision_ctx) and new (vision_context)
    vision = vision_ctx or kwargs.get("vision_context") or kwargs.get("vision")

    parts = [
        "## Semantic Translation",
        f"翻译为{target_lang}语义翻译（不做人格化表演）",
        PromptBuilder._TRANSLATION_RULES,
    ]
    if vision and vision.get("box_type"):
        parts.append(f"- 文本框类型：{vision['box_type']}（旁白/拟声词/招牌）")
    if cultural_ctx and not isinstance(cultural_ctx, str) and cultural_ctx.get("translation_context"):
        parts.append("## 文化约束")
        parts.append(cultural_ctx["translation_context"])
    parts.extend([f"原文: {source_text}"])
    parts.append(f"JSON: {_json.dumps(PromptBuilder._SEMANTIC_JSON_SCHEMA, ensure_ascii=False)}")
    return "\n".join(parts)


def _build_persona_render_prompt(
    source_text: str = "",
    semantic: Any = None,
    memory_ctx: dict = None,
    target_lang: str = "zh-CN",
    relationship_ctx: str = "",
    **kwargs,
) -> str:
    """Legacy alias - supports old parameter names."""
    from mga.models.translation import SemanticTranslation

    if memory_ctx is None:
        memory_ctx = {}

    # Parse semantic from various formats
    if semantic is None:
        semantic = SemanticTranslation(text=kwargs.get("semantic_text", ""))
    elif isinstance(semantic, dict):
        semantic = SemanticTranslation(**semantic)
    elif not isinstance(semantic, SemanticTranslation):
        semantic = SemanticTranslation(text=str(semantic))

    # Support both old and new parameter names
    # relationship_ctx (positional) -> relationship (kwarg)
    relationship = relationship_ctx or kwargs.get("relationship", kwargs.get("relationship_context", ""))
    vision = kwargs.get("vision_context", kwargs.get("vision_ctx", kwargs.get("vision")))
    listener = kwargs.get("listener")
    scene = kwargs.get("scene", "")

    # Build persona prompt manually to include provisional_speaker
    parts = [
        "## Persona Rendering",
        "将语义翻译渲染为最终嵌字文本",
        "## 人格规则",
        "- 仅调整语气、句式、敬语、口癖",
    ]
    if semantic.must_preserve:
        parts.append(f"- 不得改变事实、专名或must_preserve内容")
        parts.append(f"- 必须保留: {', '.join(semantic.must_preserve)}")
    else:
        parts.append("- 不得改变事实、专名或must_preserve内容")

    parts.extend([f"原文: {source_text}", f"语义: {semantic.text}"])

    # Character profile
    if memory_ctx:
        parts.append("## 角色档案")
        if memory_ctx.get("name_jp"):
            parts.append(f"- 名: {memory_ctx['name_jp']}→{memory_ctx.get('name_zh', memory_ctx['name_jp'])}")
        if memory_ctx.get("archetype"):
            parts.append(f"- 型: {memory_ctx['archetype']}")
        if memory_ctx.get("speech_patterns"):
            patterns = "; ".join(f"{k}={v}" for k, v in memory_ctx["speech_patterns"].items())
            parts.append(f"- 语式: {patterns}")
        if memory_ctx.get("catchphrases"):
            parts.append(f"- 口癖: {', '.join(memory_ctx['catchphrases'])}")
        if memory_ctx.get("tone_spectrum"):
            tones = "; ".join(f"{k}={v}" for k, v in memory_ctx["tone_spectrum"].items())
            parts.append(f"- 语气: {tones}")

    if relationship:
        parts.append(relationship)
    if listener:
        parts.append(f"- 听者: {listener}")
    if scene:
        parts.append(f"## 场景\n{scene}")
    if vision:
        if vision.get("provisional_speaker"):
            parts.append(f"临时说话人：{vision['provisional_speaker']}")
        if vision.get("voice_hint"):
            parts.append(f"语气: {vision['voice_hint']}")

    parts.append(f"JSON: {_json.dumps(PromptBuilder._PERSONA_JSON_SCHEMA, ensure_ascii=False)}")
    return "\n".join(parts)


# Export for backward compatibility
__all__ = [
    "BubbleContext", "TranslationService", "PromptBuilder",
    "_build_translation_prompt", "_build_semantic_translation_prompt",
    "_build_persona_render_prompt",
]


# =============================================================================
# Factory function for easy instantiation
# =============================================================================

def create_translation_service(config: ProjectConfig) -> TranslationService:
    """Create a fully configured TranslationService."""
    provider_cascade = ProviderCascade(config, "translation")

    project_dir = Path(config.working_dir) if config.working_dir else Path(".")
    cultural_adapter = CulturalAdapter(project_dir)
    memory_updater = CharacterMemoryUpdater(project_dir)

    # Get cache from config if available
    llm_cache = None
    if config.llm_cache_enabled:
        try:
            from mga.cache import LLMCache
            llm_cache = LLMCache(cache_dir=config.llm_cache_dir, enabled=True)
        except Exception as e:
            logger.warning(f"Failed to initialize cache: {e}")

    return TranslationService(
        provider_cascade=provider_cascade,
        cultural_adapter=cultural_adapter,
        memory_updater=memory_updater,
        llm_cache=llm_cache,
    )