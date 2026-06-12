"""Generic OpenAI-compatible provider for custom endpoints.

This provider supports any OpenAI-compatible API endpoint, automatically
detecting vision capabilities through capability probing.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Dict, List, Optional

import openai

from ..artifacts import ArtifactStore
from ..exceptions import ProviderError, ProviderResponseError
from ..models import BoundingBox, Bubble, Page, TranslationCandidate, Utterance
from .base import LLMProvider

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = (
    "You are an expert manga OCR system. Extract all Japanese text bubbles from the image. "
    'Return JSON: {"bubbles": [{"bbox": {"x":float, "y":float, "width":float, "height":float}, '
    '"source_text": str, "reading_order": int, "speaker_name": str|null, "speaker_id": str|null, '
    '"tone": str|null, "notes": str|null}], "scene_summary": str}. '
    "Bbox values are 0-1 normalized coordinates. Reading order is right-to-left, top-to-bottom. "
    "Respond ONLY with valid JSON, no markdown fences."
)

TRANSLATION_PROMPT = (
    "You are an expert manga translator (Japanese to Simplified Chinese). "
    "Translate the utterances below, preserving speaker tone and nuance. "
    'Return JSON: {"translations": [{"bubble_id": str, "text": str, '
    '"rationale": str, "confidence": float 0-1}]}. Respond ONLY with valid JSON.'
)

VISION_CAPABILITY_PROMPT = "Hello"


def _parse_json(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("```")).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(f"Failed to parse JSON from LLM response: {exc}") from exc


def _usage(response: Any) -> dict[str, int]:
    u = getattr(response, "usage", None)
    if u is None:
        return {}
    return {"prompt_tokens": getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
            "total_tokens": getattr(u, "total_tokens", 0)}


def _content(response: Any) -> str:
    c = response.choices[0].message.content
    if c is None:
        raise ProviderResponseError("Provider returned empty content")
    return c


def _make_image_parts(images: List[bytes]) -> list[dict[str, Any]]:
    return [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64.standard_b64encode(i).decode('ascii')}"}}
            for i in images]


def _inject_images(messages: List[Dict[str, Any]], image_parts: list[dict[str, Any]]) -> List[Dict[str, Any]]:
    result = [dict(m) for m in messages]
    if result and result[-1].get("role") == "user":
        existing = result[-1].get("content", "")
        if isinstance(existing, str):
            result[-1]["content"] = [{"type": "text", "text": existing}, *image_parts]
        elif isinstance(existing, list):
            existing.extend(image_parts)
    return result


def _make_bbox(raw: dict) -> BoundingBox:
    b = raw.get("bbox", {})
    return BoundingBox(x=b.get("x", 0.0), y=b.get("y", 0.0), width=b.get("width", 0.0), height=b.get("height", 0.0))


def _make_candidate(raw: dict) -> TranslationCandidate:
    return TranslationCandidate(bubble_id=raw.get("bubble_id", ""), text=raw.get("text", ""),
                                rationale=raw.get("rationale", ""), confidence=float(raw.get("confidence", 0.0)))


class GenericOpenAIProvider(LLMProvider):
    """Generic OpenAI-compatible provider with auto vision detection.

    Supports any OpenAI-compatible API endpoint. Vision support is automatically
    detected unless explicitly configured.

    Args:
        api_key: API key for authentication
        api_key_env: Environment variable containing API key
        base_url: API base URL (e.g., https://api.example.com/v1)
        base_url_env: Environment variable containing base URL
        model: Default model identifier
        vision_model: Model for vision tasks (auto-detected if None)
        text_model: Model for text-only tasks (defaults to model)
        supports_vision: Override auto-detection for vision capability
        temperature: Default sampling temperature
        max_retries: Maximum retry attempts
    """

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        api_key_env: Optional[str] = None,
        base_url: Optional[str] = None,
        base_url_env: Optional[str] = None,
        model: Optional[str] = None,
        vision_model: Optional[str] = None,
        text_model: Optional[str] = None,
        supports_vision: Optional[bool] = None,
        temperature: float = 0.2,
        max_retries: int = 2,
    ) -> None:
        resolved_api_key = api_key
        if resolved_api_key is None and api_key_env:
            resolved_api_key = os.getenv(api_key_env)

        resolved_base_url = base_url
        if resolved_base_url is None and base_url_env:
            resolved_base_url = os.getenv(base_url_env)

        self._model = vision_model or model
        self._translate_model = text_model or model
        self._temperature = temperature
        self._max_retries = max_retries
        self._explicit_vision = supports_vision

        if not resolved_base_url:
            raise ProviderError("GenericOpenAIProvider requires base_url")

        self._client = openai.OpenAI(
            api_key=resolved_api_key,
            base_url=resolved_base_url,
            max_retries=max_retries,
        )

        # Auto-detect vision support if not explicitly set
        self._vision_detected: Optional[bool] = None

    def _check_vision_capability(self) -> bool:
        """Probe the API for vision capability by sending a simple vision request."""
        if self._vision_detected is not None:
            return self._vision_detected

        try:
            # Create a minimal base64 transparent 1x1 PNG
            minimal_png = base64.standard_b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            )
            resp = self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": [{"type": "text", "text": VISION_CAPABILITY_PROMPT}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64.standard_b64encode(minimal_png).decode('ascii')}"}}]}],
                max_tokens=5,
            )
            self._vision_detected = True
            logger.debug("Vision capability detected for %s", self._model)
        except Exception as e:
            logger.debug("Vision capability not detected for %s: %s", self._model, e)
            self._vision_detected = False

        return self._vision_detected

    # -- abstract properties ------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model or "unknown"

    @property
    def supports_vision(self) -> bool:
        if self._explicit_vision is not None:
            return self._explicit_vision
        return self._check_vision_capability()

    @property
    def cost_per_1k_tokens(self) -> Optional[float]:
        return None  # Generic provider - pricing unknown

    # -- LLMProvider text methods -------------------------------------------

    def chat(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        resp = self._client.chat.completions.create(
            model=self._model, messages=messages,
            temperature=kwargs.pop("temperature", self._temperature), **kwargs,
        )
        return _content(resp)

    def chat_structured(self, messages: List[Dict[str, Any]], schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        resp = self._client.chat.completions.create(
            model=self._model, messages=messages, response_format={"type": "json_object"},
            temperature=kwargs.pop("temperature", self._temperature), **kwargs,
        )
        return _parse_json(_content(resp))

    def vision(self, messages: List[Dict[str, Any]], images: List[bytes], **kwargs: Any) -> str:
        resp = self._client.chat.completions.create(
            model=self._model, messages=_inject_images(messages, _make_image_parts(images)),
            temperature=kwargs.pop("temperature", self._temperature), **kwargs,
        )
        return _content(resp)

    def vision_structured(self, messages: List[Dict[str, Any]], images: List[bytes], schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        resp = self._client.chat.completions.create(
            model=self._model, messages=_inject_images(messages, _make_image_parts(images)),
            response_format={"type": "json_object"},
            temperature=kwargs.pop("temperature", self._temperature), **kwargs,
        )
        return _parse_json(_content(resp))

    # -- domain-specific benchmark methods ----------------------------------

    def vision_extract(self, page: Page, *, store: Optional[ArtifactStore] = None) -> tuple[Page, dict]:
        """Extract text bubbles from a manga page image via vision model."""
        if not page.image.path:
            raise ProviderError("Page has no image path set")

        from pathlib import Path
        b64 = base64.standard_b64encode(Path(page.image.path).read_bytes()).decode("ascii")
        media_type = "image/png"

        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": "Extract all Japanese text bubbles from this manga page."},
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
                ]},
            ],
            response_format={"type": "json_object"},
            temperature=self._temperature,
        )

        parsed = _parse_json(_content(resp))
        raw_bubbles = parsed.get("bubbles", [])
        bubbles = [
            Bubble(
                bubble_id=raw.get("bubble_id", f"b{i + 1}"),
                bbox=_make_bbox(raw),
                source_text=raw.get("source_text", ""),
                reading_order=raw.get("reading_order", i),
                speaker_id=raw.get("speaker_id"),
                speaker_name=raw.get("speaker_name"),
                tone=raw.get("tone"),
                notes=raw.get("notes"),
            )
            for i, raw in enumerate(raw_bubbles)
        ]

        result_page = Page(
            page_id=page.page_id, page_index=page.page_index, image=page.image,
            source_lang=page.source_lang, bubbles=bubbles,
            scene_summary=parsed.get("scene_summary", ""),
        )
        meta: dict[str, Any] = {"model": self._model, "bubble_count": len(bubbles), "usage": _usage(resp)}

        if store is not None:
            store.write_page(page.page_id, result_page)
            logger.info("vision_extract: wrote page %s (%d bubbles)", page.page_id, len(bubbles))

        return result_page, meta

    def translate(
        self, page: Page, utterances: List[Utterance], *, store: Optional[ArtifactStore] = None,
    ) -> tuple[list[TranslationCandidate], dict]:
        """Translate utterances for a page using text model."""
        payload = {
            "scene_summary": page.scene_summary,
            "utterances": [
                {"bubble_id": u.bubble_id, "source_text": u.source_text, "speaker": u.speaker,
                 "tone": u.tone, "context_notes": u.context_notes}
                for u in utterances
            ],
        }

        resp = self._client.chat.completions.create(
            model=self._translate_model or self._model,
            messages=[
                {"role": "system", "content": TRANSLATION_PROMPT},
                {"role": "user", "content": f"Translate these utterances into Simplified Chinese:\n\n{json.dumps(payload, ensure_ascii=False)}"},
            ],
            response_format={"type": "json_object"},
            temperature=self._temperature,
        )

        parsed = _parse_json(_content(resp))
        raw_list = parsed.get("translations", parsed if isinstance(parsed, list) else [])
        translations = [_make_candidate(r) for r in raw_list]
        meta: dict[str, Any] = {"model": self._translate_model or self._model, "translation_count": len(translations), "usage": _usage(resp)}

        if store is not None:
            store.write_translations(page.page_id, translations)
            logger.info("translate: wrote %d translations for page %s", len(translations), page.page_id)

        return translations, meta