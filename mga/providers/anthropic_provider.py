"""Anthropic Claude LLM provider."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import anthropic

from .base import LLMProvider

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-sonnet-4-20250514"
_JSON_SUFFIX = (
    "\n\nRespond ONLY with valid JSON matching the requested schema. "
    "No markdown fences, no commentary."
)

_TRANSLATION_SCHEMA: Dict[str, Any] = {
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
            },
        }
    },
}

_EXTRACTION_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "bubbles": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "bubble_id": {"type": "string"},
                    "source_text": {"type": "string"},
                    "bbox": {
                        "type": "object",
                        "properties": {
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "width": {"type": "number"},
                            "height": {"type": "number"},
                        },
                    },
                    "reading_order": {"type": "integer"},
                    "speaker_name": {"type": ["string", "null"]},
                },
            },
        }
    },
}


def _read_image(path: str) -> bytes:
    if path:
        return Path(path).read_bytes()
    return b""


class AnthropicProvider(LLMProvider):
    """Anthropic Claude provider using the Messages API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = _DEFAULT_MODEL,
        **kwargs: Any,
    ) -> None:
        self._model = model
        self._max_tokens = kwargs.pop("max_tokens", 4096)
        self._client = anthropic.Anthropic(api_key=api_key, **kwargs)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def supports_vision(self) -> bool:
        return True

    @property
    def cost_per_1k_tokens(self) -> Optional[float]:
        costs = {"claude-sonnet-4-20250514": 0.003, "claude-3-5-sonnet-20241022": 0.003, "claude-3-opus-20240229": 0.015}
        return costs.get(self._model)

    # -- message formatting --------------------------------------------------

    def _extract_system(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        for msg in messages:
            if msg.get("role") == "system":
                return msg.get("content")
        return None

    def _format_messages(
        self,
        messages: List[Dict[str, Any]],
        images: Optional[List[bytes]] = None,
        schema: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                continue
            content = msg.get("content", "")
            if isinstance(content, str):
                blocks: List[Dict[str, Any]] = [{"type": "text", "text": content}]
            elif isinstance(content, list):
                blocks = list(content)
            else:
                blocks = [{"type": "text", "text": str(content)}]
            out.append({"role": role, "content": blocks})

        if images:
            img_blocks = [
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(i).decode()}}
                for i in images
            ]
            for msg in reversed(out):
                if msg["role"] == "user":
                    msg["content"] = img_blocks + msg["content"]  # type: ignore[operator]
                    break

        if schema and out:
            out[-1]["content"].append({  # type: ignore[union-attr]
                "type": "text",
                "text": "Return a JSON object matching this schema:\n" + json.dumps(schema, indent=2) + _JSON_SUFFIX,
            })
        return out

    # -- low-level call ------------------------------------------------------

    def _call(
        self,
        messages: List[Dict[str, Any]],
        images: Optional[List[bytes]] = None,
        schema: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        params: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": kwargs.pop("max_tokens", self._max_tokens),
            "messages": self._format_messages(messages, images=images, schema=schema),
        }
        system = self._extract_system(messages)
        if system:
            params["system"] = system
        params.update(kwargs)
        resp = self._client.messages.create(**params)
        return resp.content[0].text if resp.content else ""

    def _parse_json(self, text: str) -> Dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned[cleaned.index("\n") + 1 :]
            if cleaned.endswith("```"):
                cleaned = cleaned[: -3]
        try:
            return json.loads(cleaned.strip())
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from model output")
            return {"raw": text}

    # -- ABC implementation --------------------------------------------------

    def chat(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        return self._call(messages, **kwargs)

    def chat_structured(self, messages: List[Dict[str, Any]], schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        return self._parse_json(self._call(messages, schema=schema, **kwargs))

    def vision(self, messages: List[Dict[str, Any]], images: List[bytes], **kwargs: Any) -> str:
        return self._call(messages, images=images, **kwargs)

    def vision_structured(self, messages: List[Dict[str, Any]], images: List[bytes], schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        return self._parse_json(self._call(messages, images=images, schema=schema, **kwargs))

    # -- benchmark convenience methods ---------------------------------------

    def vision_extract(self, page: Any, store: Any) -> Dict[str, Any]:
        raw = _read_image(getattr(page.image, "path", ""))
        messages = [
            {"role": "system", "content": "You are an expert manga OCR assistant. Identify every speech bubble and text region."},
            {"role": "user", "content": "Extract all text bubbles from this manga page. Return JSON with a 'bubbles' array."},
        ]
        result = self.vision_structured(messages, [raw] if raw else [], _EXTRACTION_SCHEMA)
        if hasattr(store, "write_page"):
            store.write_page(page.page_id, result)
        return result

    def translate(self, page: Any, utterances: List[Any], store: Any) -> List[Any]:
        from mga.models import TranslationCandidate

        context = "\n".join(f"[{u.bubble_id}] {u.source_text}" for u in utterances)
        messages = [
            {"role": "system", "content": "You are a professional manga translator. Translate Japanese to English naturally, preserving tone and speaker voice."},
            {"role": "user", "content": f"Translate these utterances:\n{context}\n\nReturn JSON with a 'translations' array."},
        ]
        result = self.vision_structured(messages, [], _TRANSLATION_SCHEMA)
        candidates = [TranslationCandidate(**t) for t in result.get("translations", [])]
        if hasattr(store, "write_translations"):
            store.write_translations(page.page_id, result)
        return candidates

    def direct_translate_page(self, page: Any, store: Any) -> List[Any]:
        from mga.models import TranslationCandidate

        raw = _read_image(getattr(page.image, "path", ""))
        bubble_desc = "\n".join(f"- {b.bubble_id}: '{b.source_text}'" for b in page.bubbles)
        messages = [
            {"role": "system", "content": "You are a professional manga translator. Given a manga page image and OCR text, produce natural English translations."},
            {"role": "user", "content": f"Bubbles detected:\n{bubble_desc}\n\nTranslate each bubble. Return JSON with a 'translations' array."},
        ]
        result = self.vision_structured(messages, [raw] if raw else [], _TRANSLATION_SCHEMA)
        candidates = [TranslationCandidate(**t) for t in result.get("translations", [])]
        if hasattr(store, "write_translations"):
            store.write_translations(page.page_id, result)
        return candidates
