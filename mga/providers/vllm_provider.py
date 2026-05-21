"""vLLM LLM provider (OpenAI-compatible API, text + vision)."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..artifacts import ArtifactStore
from ..models import BoundingBox, Bubble, Page, TranslationCandidate, Utterance
from .base import LLMProvider

logger = logging.getLogger(__name__)

# Compact JSON schemas for structured outputs
_BBOX_PROPS = {"x": {"type": "number"}, "y": {"type": "number"}, "width": {"type": "number"}, "height": {"type": "number"}}
_BBOX = {"type": "object", "properties": _BBOX_PROPS}

_EXTRACT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {"bubbles": {"type": "array", "items": {"type": "object", "properties": {
        "bubble_id": {"type": "string"}, "bbox": _BBOX, "source_text": {"type": "string"},
        "reading_order": {"type": "integer"}, "speaker_name": {"type": ["string", "null"]},
        "tone": {"type": ["string", "null"]}, "notes": {"type": ["string", "null"]},
    }, "required": ["bubble_id", "bbox", "source_text", "reading_order"]}}},
    "required": ["bubbles"],
}

_TRANSLATE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {"translations": {"type": "array", "items": {"type": "object", "properties": {
        "bubble_id": {"type": "string"}, "text": {"type": "string"},
        "rationale": {"type": "string"}, "confidence": {"type": "number"},
    }, "required": ["bubble_id", "text", "rationale", "confidence"]}}},
    "required": ["translations"],
}

_DIRECT_TRANSLATE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {"translations": {"type": "array", "items": {"type": "object", "properties": {
        "bubble_id": {"type": "string"}, "bbox": _BBOX, "source_text": {"type": "string"},
        "text": {"type": "string"}, "reading_order": {"type": "integer"},
        "speaker_name": {"type": ["string", "null"]}, "tone": {"type": ["string", "null"]},
        "rationale": {"type": "string"}, "confidence": {"type": "number"},
    }, "required": ["bubble_id", "source_text", "text", "reading_order", "rationale", "confidence"]}}},
    "required": ["translations"],
}

_EXTRACT_SYS = (
    "You are a manga OCR assistant. Analyze the manga page image and extract all text bubbles. "
    "Return JSON matching the provided schema. Use normalized coordinates (0.0-1.0) for bounding boxes. "
    "Assign reading_order starting from 1 in natural reading order."
)
_TRANSLATE_SYS = "You are a professional manga translation assistant. Translate each utterance faithfully, preserving tone and register. Return JSON matching the provided schema."
_DIRECT_SYS = (
    "You are a manga translation assistant. Analyze the manga page image, "
    "extract all text bubbles, and translate them to the target language. "
    "Return JSON matching the provided schema. Use normalized coordinates (0.0-1.0) for bounding boxes."
)


class VLLMProvider(LLMProvider):
    """vLLM provider via OpenAI-compatible API (text + optional vision)."""

    def __init__(self, *, model: str = "Qwen/Qwen2-VL-7B-Instruct",
                 base_url: str = "http://localhost:8000/v1", api_key: str = "token-abc123",
                 target_lang: str = "zh-CN", vision_enabled: bool = True) -> None:
        try:
            import openai  # noqa: F401
        except ImportError as exc:
            raise ImportError("The 'openai' package is required for VLLMProvider. pip install openai") from exc
        self._model = model
        self._target_lang = target_lang
        self._vision_enabled = vision_enabled
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def supports_vision(self) -> bool:
        return self._vision_enabled

    @property
    def cost_per_1k_tokens(self) -> float | None:
        return None

    # -- ABC abstract methods -------------------------------------------------

    def chat(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        resp = self._client.chat.completions.create(model=self._model, messages=messages, **kwargs)
        return resp.choices[0].message.content or ""

    def chat_structured(self, messages: List[Dict[str, Any]], schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        kwargs.setdefault("response_format", {"type": "json_object"})
        raw = self.chat(messages, **kwargs)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Failed to parse structured response, returning raw text")
            return {"raw": raw}

    def vision(self, messages: List[Dict[str, Any]], images: List[bytes], **kwargs: Any) -> str:
        formatted = _format_vision_messages(messages, images)
        resp = self._client.chat.completions.create(model=self._model, messages=formatted, **kwargs)
        return resp.choices[0].message.content or ""

    def vision_structured(self, messages: List[Dict[str, Any]], images: List[bytes],
                          schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        kwargs.setdefault("response_format", {"type": "json_object"})
        raw = self.vision(messages, images, **kwargs)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Failed to parse structured vision response")
            return {"raw": raw}

    # -- Benchmark methods ----------------------------------------------------

    def vision_extract(self, page: Page, *, store: ArtifactStore) -> tuple[Page, str]:
        """Extract text bubbles from a manga page image using vision."""
        img = _read_image_bytes(page.image.path)
        msgs = [{"role": "system", "content": _EXTRACT_SYS},
                {"role": "user", "content": f"Source language: {page.source_lang}\nExtract all text bubbles from this manga page."}]
        result = self.vision_structured(msgs, [img], schema=_EXTRACT_SCHEMA)
        bubbles = [_item_to_bubble(item) for item in result.get("bubbles", [])]
        analyzed = Page(page_id=page.page_id, page_index=page.page_index, image=page.image,
                        source_lang=page.source_lang, bubbles=bubbles, scene_summary=page.scene_summary)
        return analyzed, store.write_page(page.page_id, analyzed)

    def translate(self, page: Page, utterances: List[Utterance], *, store: ArtifactStore) -> tuple[list[TranslationCandidate], str]:
        """Translate utterances from page context (text-only path)."""
        ctx = f"Scene context: {page.scene_summary}\n" if page.scene_summary else ""
        lines = []
        for u in utterances:
            line = f"- [{u.bubble_id}] {u.source_text}"
            if u.speaker:
                line += f" (speaker: {u.speaker})"
            if u.tone:
                line += f" (tone: {u.tone})"
            lines.append(line)
        user_msg = (f"Source language: {page.source_lang}\nTarget language: {self._target_lang}\n{ctx}"
                    "\nUtterances to translate:\n" + "\n".join(lines))
        msgs = [{"role": "system", "content": _TRANSLATE_SYS}, {"role": "user", "content": user_msg}]
        result = self.chat_structured(msgs, schema=_TRANSLATE_SCHEMA)
        translations = [_item_to_candidate(item) for item in result.get("translations", [])]
        return translations, store.write_translations(page.page_id, translations)

    def direct_translate_page(self, page: Page, *, store: ArtifactStore) -> tuple[list[TranslationCandidate], str]:
        """Extract and translate in a single vision pass."""
        img = _read_image_bytes(page.image.path)
        user_msg = (f"Source language: {page.source_lang}\nTarget language: {self._target_lang}\n"
                    "Extract all text bubbles and translate them.")
        msgs = [{"role": "system", "content": _DIRECT_SYS}, {"role": "user", "content": user_msg}]
        result = self.vision_structured(msgs, [img], schema=_DIRECT_TRANSLATE_SCHEMA)
        translations = [_item_to_candidate(item) for item in result.get("translations", [])]
        return translations, store.write_translations(page.page_id, translations)


# -- Helpers ------------------------------------------------------------------

def _read_image_bytes(path: str) -> bytes:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    return p.read_bytes()

def _item_to_bubble(item: dict) -> Bubble:
    b = item.get("bbox", {})
    return Bubble(
        bubble_id=item.get("bubble_id", ""),
        bbox=BoundingBox(x=float(b.get("x", 0)), y=float(b.get("y", 0)),
                         width=float(b.get("width", 0)), height=float(b.get("height", 0))),
        source_text=item.get("source_text", ""),
        reading_order=int(item.get("reading_order", 0)),
        speaker_name=item.get("speaker_name"), tone=item.get("tone"), notes=item.get("notes"),
    )

def _item_to_candidate(item: dict) -> TranslationCandidate:
    return TranslationCandidate(
        bubble_id=item.get("bubble_id", ""), text=item.get("text", ""),
        rationale=item.get("rationale", ""), confidence=float(item.get("confidence", 0.0)),
    )

def _format_vision_messages(messages: List[Dict[str, Any]], images: List[bytes]) -> List[Dict[str, Any]]:
    """Convert messages to OpenAI vision format with base64 image URLs."""
    formatted, image_added = [], False
    for msg in messages:
        if msg["role"] == "user" and not image_added and images:
            content: Any = [{"type": "text", "text": msg["content"]}]
            for img_bytes in images:
                b64 = base64.b64encode(img_bytes).decode("ascii")
                content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}})
            formatted.append({"role": "user", "content": content})
            image_added = True
        else:
            formatted.append(msg)
    return formatted
