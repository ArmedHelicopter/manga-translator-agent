"""OpenAI provider for LLM-powered extraction and translation."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, List

import openai

from ..artifacts import ArtifactStore
from ..exceptions import ProviderError, ProviderResponseError
from ..models import BoundingBox, Bubble, Page, TranslationCandidate, Utterance
from .base import LLMProvider

logger = logging.getLogger(__name__)

VISION_MODEL = "gpt-4o"
TRANSLATE_MODEL = "gpt-4o-mini"

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

DIRECT_TRANSLATION_PROMPT = (
    "Translate all visible Japanese text on this manga page into Simplified Chinese. "
    'Return a JSON array: [{"bubble_id": str, "text": str, "rationale": str, '
    '"confidence": float 0-1}] in reading order (right-to-left, top-to-bottom). '
    "Respond ONLY with valid JSON, no markdown fences."
)


# -- helpers ----------------------------------------------------------------


def _encode_image(image_path: str) -> tuple[str, str]:
    p = Path(image_path)
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    return base64.standard_b64encode(p.read_bytes()).decode("ascii"), mime.get(p.suffix.lower(), "image/png")


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
        raise ProviderResponseError("OpenAI returned empty content")
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


# -- provider ---------------------------------------------------------------


class OpenAIProvider(LLMProvider):
    """Concrete LLM provider backed by the OpenAI API.

    Supports text chat, structured output, vision, and domain-specific
    benchmark methods: ``vision_extract``, ``translate``,
    ``direct_translate_page``.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        translate_model: str | None = None,
        temperature: float = 0.2,
        max_retries: int = 2,
    ) -> None:
        self._model = model or VISION_MODEL
        self._translate_model = translate_model or TRANSLATE_MODEL
        self._temperature = temperature
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url, max_retries=max_retries)

    # -- abstract properties ------------------------------------------------

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def supports_vision(self) -> bool:
        return True

    @property
    def cost_per_1k_tokens(self) -> float | None:
        return {VISION_MODEL: 0.005, TRANSLATE_MODEL: 0.00015}.get(self._model)

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

    def vision_extract(self, page: Page, *, store: ArtifactStore | None = None) -> tuple[Page, dict]:
        """Extract text bubbles from a manga page image via GPT-4o vision."""
        if not page.image.path:
            raise ProviderError("Page has no image path set")

        b64, media_type = _encode_image(page.image.path)
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
        self, page: Page, utterances: List[Utterance], *, store: ArtifactStore | None = None,
    ) -> tuple[list[TranslationCandidate], dict]:
        """Translate utterances for a page using GPT-4o-mini."""
        payload = {
            "scene_summary": page.scene_summary,
            "utterances": [
                {"bubble_id": u.bubble_id, "source_text": u.source_text, "speaker": u.speaker,
                 "tone": u.tone, "context_notes": u.context_notes}
                for u in utterances
            ],
        }

        resp = self._client.chat.completions.create(
            model=self._translate_model,
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
        meta: dict[str, Any] = {"model": self._translate_model, "translation_count": len(translations), "usage": _usage(resp)}

        if store is not None:
            store.write_translations(page.page_id, translations)
            logger.info("translate: wrote %d translations for page %s", len(translations), page.page_id)

        return translations, meta

    def direct_translate_page(
        self, page: Page, *, store: ArtifactStore | None = None,
    ) -> tuple[list[TranslationCandidate], dict]:
        """Translate a full manga page image directly via GPT-4o vision."""
        if not page.image.path:
            raise ProviderError("Page has no image path set")

        b64, media_type = _encode_image(page.image.path)
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": DIRECT_TRANSLATION_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": "Translate all Japanese text on this manga page into Simplified Chinese."},
                    {"type": "image_url", "image_url": {"url": f"data:{media_type};base64,{b64}"}},
                ]},
            ],
            response_format={"type": "json_object"},
            temperature=self._temperature,
        )

        parsed = _parse_json(_content(resp))
        raw_list = parsed if isinstance(parsed, list) else parsed.get("translations", [])
        translations = [_make_candidate(r) for r in raw_list]
        meta: dict[str, Any] = {"model": self._model, "translation_count": len(translations), "usage": _usage(resp)}

        if store is not None:
            store.write_translations(page.page_id, translations)
            logger.info("direct_translate_page: wrote %d translations for page %s", len(translations), page.page_id)

        return translations, meta
