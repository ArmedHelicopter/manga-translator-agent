"""DeepSeek LLM provider (OpenAI-compatible, text-only)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from ..artifacts import ArtifactStore
from ..models import (
    BoundingBox,
    Bubble,
    Page,
    PageImage,
    TranslationCandidate,
    Utterance,
)
from .base import LLMProvider

logger = logging.getLogger(__name__)

_TRANSLATE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "bubble_id": {"type": "string"},
                    "text": {"type": "string"},
                    "rationale": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["bubble_id", "text", "rationale", "confidence"],
            },
        }
    },
    "required": ["translations"],
}

_TRANSLATE_SYSTEM_PROMPT = (
    "You are a professional manga translation assistant. "
    "Translate each utterance faithfully, preserving tone and register. "
    "Return JSON matching the provided schema."
)


class DeepSeekProvider(LLMProvider):
    """DeepSeek provider via the OpenAI-compatible API (text-only, no vision)."""

    def __init__(
        self,
        *,
        model: str = "deepseek-chat",
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com/v1",
    ) -> None:
        try:
            import openai  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required for DeepSeekProvider. "
                "Install it with: pip install openai"
            ) from exc

        self._model = model
        self._client = openai.OpenAI(
            api_key=api_key or "sk-placeholder",
            base_url=base_url,
        )

    # -- ABC properties -------------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def supports_vision(self) -> bool:
        return False

    @property
    def cost_per_1k_tokens(self) -> Optional[float]:
        return 0.0014  # deepseek-chat pricing estimate

    # -- ABC abstract methods -------------------------------------------------

    def chat(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            **kwargs,
        )
        return response.choices[0].message.content or ""

    def chat_structured(
        self,
        messages: List[Dict[str, Any]],
        schema: Dict[str, Any],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        kwargs.setdefault("response_format", {"type": "json_object"})
        raw = self.chat(messages, **kwargs)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Failed to parse structured response, returning raw text")
            return {"raw": raw}

    def vision(self, messages: List[Dict[str, Any]], images: List[bytes], **kwargs: Any) -> str:
        raise NotImplementedError("DeepSeek does not support vision inputs")

    def vision_structured(
        self,
        messages: List[Dict[str, Any]],
        images: List[bytes],
        schema: Dict[str, Any],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        raise NotImplementedError("DeepSeek does not support vision inputs")

    # -- Benchmark methods ----------------------------------------------------

    def translate(
        self,
        page: Page,
        utterances: List[Utterance],
        *,
        store: ArtifactStore,
    ) -> tuple[list[TranslationCandidate], str]:
        """Translate utterances from page context (text-only, no vision)."""
        context_parts = []
        if page.scene_summary:
            context_parts.append(f"Scene context: {page.scene_summary}")

        utterance_lines = []
        for u in utterances:
            line = f"- [{u.bubble_id}] {u.source_text}"
            if u.speaker:
                line += f" (speaker: {u.speaker})"
            if u.tone:
                line += f" (tone: {u.tone})"
            utterance_lines.append(line)

        user_msg = (
            f"Source language: {page.source_lang}\n"
            f"Target language: {getattr(self, '_target_lang', 'zh-CN')}\n"
            + "\n".join(context_parts)
            + "\n\nUtterances to translate:\n"
            + "\n".join(utterance_lines)
        )

        messages = [
            {"role": "system", "content": _TRANSLATE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        result = self.chat_structured(messages, schema=_TRANSLATE_SCHEMA)
        translations = []
        for item in result.get("translations", []):
            translations.append(
                TranslationCandidate(
                    bubble_id=item.get("bubble_id", ""),
                    text=item.get("text", ""),
                    rationale=item.get("rationale", ""),
                    confidence=float(item.get("confidence", 0.0)),
                )
            )

        artifact_path = store.write_translations(page.page_id, translations)
        return translations, artifact_path

    def vision_extract(
        self,
        page: Page,
        *,
        store: ArtifactStore,
    ) -> tuple[Page, str]:
        raise NotImplementedError("DeepSeek does not support vision extraction")

    def direct_translate_page(
        self,
        page: Page,
        *,
        store: ArtifactStore,
    ) -> tuple[list[TranslationCandidate], str]:
        raise NotImplementedError("DeepSeek does not support direct page translation")
