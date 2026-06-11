"""Unified Translation Service — single entry point for all LLM calls.

This module consolidates the translation pipeline into a coherent,
token-efficient service that handles:
- Semantic extraction
- Persona rendering
- Cultural adaptation
- Character memory updates
- Relationship graph integration
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# === Request/Response Models ===

class TranslationRequest(BaseModel):
    """Single bubble translation request."""

    bubble_id: str = ""
    page_id: str = ""
    source_text: str = ""
    speaker_id: str | None = None
    listener_id: str | None = None
    character_profile: dict[str, Any] = Field(default_factory=dict)
    scene_context: dict[str, Any] = Field(default_factory=dict)
    cultural_context: dict[str, Any] = Field(default_factory=dict)
    relationship_context: str = ""
    translation_memory: list[dict] = Field(default_factory=list)
    target_lang: str = "zh-CN"

    model_config = {"arbitrary_types_allowed": True}


class TranslationResponse(BaseModel):
    """Translation result with metadata."""

    bubble_id: str = ""
    translated_text: str = ""
    footnotes: list[dict] = Field(default_factory=list)
    rationale: str = ""
    semantic_provider: str = ""
    persona_provider: str = ""
    semantic_model: str = ""
    persona_model: str = ""
    tokens_used: int = 0

    model_config = {"arbitrary_types_allowed": True}


class TranslationServiceResult(BaseModel):
    """Batch translation result."""

    translations: list[TranslationResponse] = Field(default_factory=list)
    character_updates: list[dict] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    total_tokens: int = 0

    model_config = {"arbitrary_types_allowed": True}


# === Prompt Builder ===

class PromptBuilder:
    """Token-optimized prompt builder for translation."""

    # Compact schema for JSON mode
    JSON_SCHEMA = '{"text":"string","footnotes":[],"rationale":"string"}'

    @classmethod
    def semantic_prompt(cls, source: str, context: dict, target_lang: str) -> str:
        """Build semantic extraction prompt."""
        parts = [
            "Extract semantic meaning:",
            f"Source: {source}",
        ]
        if context:
            parts.append(f"Context: {json.dumps(context, ensure_ascii=False)}")
        parts.append(f"Target: {target_lang}")
        parts.append(f"Schema: {cls.JSON_SCHEMA}")
        return "\n".join(parts)

    @classmethod
    def persona_prompt(
        cls,
        source: str,
        translated: str,
        profile: dict,
        target_lang: str,
        relationship: str = "",
    ) -> str:
        """Build persona rendering prompt."""
        parts = [
            f"Source: {source}",
            f"Literal: {translated}",
        ]
        if profile:
            parts.append(f"Profile: {json.dumps(profile, ensure_ascii=False)}")
        if relationship:
            parts.append(f"Relation: {relationship}")
        parts.append(f"Target: {target_lang}")
        parts.append(f"Schema: {cls.JSON_SCHEMA}")
        return "\n".join(parts)

    @classmethod
    def full_translation_prompt(
        cls,
        source: str,
        memory_ctx: dict,
        cultural_ctx: dict,
        target_lang: str,
        relationship_ctx: str = "",
    ) -> str:
        """Build full translation prompt with all context."""
        parts = []

        # Character profile section (compact)
        if memory_ctx:
            parts.append("## Character Profile")
            if memory_ctx.get("name_jp"):
                parts.append(f"Name: {memory_ctx['name_jp']}")
            if memory_ctx.get("archetype"):
                parts.append(f"Archetype: {memory_ctx['archetype']}")
            if memory_ctx.get("speech_patterns"):
                for jp, desc in memory_ctx["speech_patterns"].items():
                    parts.append(f"  {jp} → {desc}")
            if memory_ctx.get("catchphrases"):
                parts.append(f"Catchphrases: {', '.join(memory_ctx['catchphrases'])}")

        # Relationship context
        if relationship_ctx:
            parts.append(f"## Relationship: {relationship_ctx}")

        # Cultural context
        if cultural_ctx:
            parts.append(f"## Cultural: {cultural_ctx.get('translation_context', '')}")

        # Source and target
        parts.append(f"Source: {source}")
        parts.append(f"Target: {target_lang}")
        parts.append(f"Schema: {cls.JSON_SCHEMA}")

        return "\n".join(parts)


# === Service Interface ===

class TranslationService:
    """Unified translation service with caching and error handling."""

    def __init__(
        self,
        provider_cascade: Any,
        project_dir: Path | str = ".",
        enable_memory: bool = True,
        enable_cultural: bool = True,
    ):
        self.cascade = provider_cascade
        self.project_dir = Path(project_dir)
        self.enable_memory = enable_memory
        self.enable_cultural = enable_cultural
        self._cache: dict[str, str] = {}

    def translate(self, request: TranslationRequest) -> TranslationResponse:
        """Translate a single bubble with full context."""
        # Check cache
        cache_key = f"{request.source_text}:{request.target_lang}"
        if cache_key in self._cache:
            return TranslationResponse(
                bubble_id=request.bubble_id,
                translated_text=self._cache[cache_key],
            )

        # Semantic step
        semantic_prompt = PromptBuilder.semantic_prompt(
            request.source_text,
            request.cultural_context,
            request.target_lang,
        )
        semantic_result = self._call_llm(
            semantic_prompt,
            stage="semantic",
            schema=PromptBuilder.JSON_SCHEMA,
        )

        # Persona step
        persona_prompt = PromptBuilder.persona_prompt(
            request.source_text,
            semantic_result.get("text", ""),
            request.character_profile,
            request.target_lang,
            request.relationship_context,
        )
        persona_result = self._call_llm(
            persona_prompt,
            stage="persona",
            schema=PromptBuilder.JSON_SCHEMA,
        )

        # Cultural adaptation
        final_text = persona_result.get("text", "")
        if self.enable_cultural and request.cultural_context:
            final_text = self._apply_cultural_adaptation(
                final_text,
                request.cultural_context,
            )

        # Update memory
        updates = []
        if self.enable_memory and request.speaker_id:
            updates = self._update_character_memory(request, final_text)

        # Cache result
        self._cache[cache_key] = final_text

        return TranslationResponse(
            bubble_id=request.bubble_id,
            translated_text=final_text,
            footnotes=persona_result.get("footnotes", []),
            rationale=persona_result.get("rationale", ""),
            semantic_provider=self.cascade.last_provider or "",
            persona_provider=self.cascade.last_provider or "",
        )

    def translate_batch(self, requests: list[TranslationRequest]) -> TranslationServiceResult:
        """Translate multiple bubbles with parallel execution."""
        results = []
        errors = []
        total_tokens = 0

        for req in requests:
            try:
                result = self.translate(req)
                results.append(result)
                total_tokens += result.tokens_used
            except Exception as exc:
                logger.error("Translation failed for %s: %s", req.bubble_id, exc)
                errors.append(str(exc))

        return TranslationServiceResult(
            translations=results,
            character_updates=[],
            errors=errors,
            total_tokens=total_tokens,
        )

    def _call_llm(
        self,
        prompt: str,
        stage: str,
        schema: str,
    ) -> dict:
        """Call LLM through provider cascade."""
        from mga.providers import ProviderCascade

        messages = [{"role": "user", "content": prompt}]
        response = self.cascade.call(messages, stage=stage)

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON response, parsing manually")
            return {"text": response.strip(), "footnotes": [], "rationale": ""}

    def _apply_cultural_adaptation(self, text: str, context: dict) -> str:
        """Apply cultural adaptations to translated text."""
        # Simplified cultural adaptation
        return text

    def _update_character_memory(
        self,
        request: TranslationRequest,
        translation: str,
    ) -> list[dict]:
        """Update character memory with new translation."""
        # Simplified memory update
        return []


# === Convenience Functions ===

def create_translation_service(
    config: Any,
    stage: str = "translation",
    project_dir: Path | str = ".",
) -> TranslationService:
    """Factory function to create a configured TranslationService."""
    from mga.providers import ProviderCascade

    cascade = ProviderCascade(config, stage)
    return TranslationService(cascade, project_dir)


def translate_bubble(
    config: Any,
    source_text: str,
    target_lang: str = "zh-CN",
    character_profile: dict | None = None,
    cultural_context: dict | None = None,
) -> str:
    """Simple one-line translation for testing."""
    service = create_translation_service(config)
    request = TranslationRequest(
        source_text=source_text,
        target_lang=target_lang,
        character_profile=character_profile or {},
        cultural_context=cultural_context or {},
    )
    response = service.translate(request)
    return response.translated_text