"""Ollama local LLM provider (text + vision via REST API)."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from ..artifacts import ArtifactStore
from ..models import BoundingBox, Bubble, Page, TranslationCandidate, Utterance
from .base import LLMProvider

logger = logging.getLogger(__name__)

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


class OllamaProvider(LLMProvider):
    """Ollama local provider with optional vision support."""

    def __init__(self, *, text_model: str = "qwen2:7b", vision_model: str = "qwen2-vl:7b",
                 base_url: str = "http://localhost:11434", target_lang: str = "zh-CN") -> None:
        self._text_model = text_model
        self._vision_model = vision_model
        self._base_url = base_url.rstrip("/")
        self._target_lang = target_lang
        self._http = httpx.Client(timeout=120.0)

    @property
    def model_name(self) -> str:
        return self._vision_model

    @property
    def supports_vision(self) -> bool:
        return True

    def _chat(self, messages: List[Dict[str, Any]], *, model: Optional[str] = None,
              images: Optional[List[str]] = None) -> str:
        ollama_msgs = []
        for msg in messages:
            omsg: Dict[str, Any] = {"role": msg["role"], "content": msg["content"]}
            if images and msg["role"] == "user":
                omsg["images"] = images
            ollama_msgs.append(omsg)
        resp = self._http.post(
            f"{self._base_url}/api/chat",
            json={"model": model or self._text_model, "messages": ollama_msgs, "stream": False},
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def _chat_structured(self, messages: List[Dict[str, Any]], schema: Dict[str, Any], *,
                         model: Optional[str] = None, images: Optional[List[str]] = None) -> Dict[str, Any]:
        # Ollama lacks native JSON schema support; append schema instruction to prompt.
        hint = "\n\nYou MUST respond with a single JSON object matching this schema:\n" + json.dumps(schema, indent=2)
        augmented = list(messages)
        if augmented and augmented[-1]["role"] == "user":
            augmented[-1] = {"role": "user", "content": augmented[-1]["content"] + hint}
        else:
            augmented.append({"role": "user", "content": f"Respond with JSON matching this schema:\n{json.dumps(schema)}"})
        return _parse_json_response(self._chat(augmented, model=model, images=images))

    def chat(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        return self._chat(messages)

    def chat_structured(self, messages: List[Dict[str, Any]], schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        return self._chat_structured(messages, schema)

    def vision(self, messages: List[Dict[str, Any]], images: List[bytes], **kwargs: Any) -> str:
        b64 = [base64.b64encode(img).decode("ascii") for img in images]
        return self._chat(messages, model=self._vision_model, images=b64)

    def vision_structured(self, messages: List[Dict[str, Any]], images: List[bytes],
                          schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        b64 = [base64.b64encode(img).decode("ascii") for img in images]
        return self._chat_structured(messages, schema, model=self._vision_model, images=b64)

    def vision_extract(self, page: Page, *, store: ArtifactStore) -> tuple[Page, str]:
        img = _read_image_bytes(page.image.path)
        msgs = [{"role": "system", "content": _EXTRACT_SYS},
                {"role": "user", "content": f"Source language: {page.source_lang}\nExtract all text bubbles from this manga page."}]
        result = self.vision_structured(msgs, [img], schema=_EXTRACT_SCHEMA)
        bubbles = [_item_to_bubble(item) for item in result.get("bubbles", [])]
        analyzed = Page(page_id=page.page_id, page_index=page.page_index, image=page.image,
                        source_lang=page.source_lang, bubbles=bubbles, scene_summary=page.scene_summary)
        return analyzed, store.write_page(page.page_id, analyzed)

    def translate(self, page: Page, utterances: List[Utterance], *, store: ArtifactStore) -> tuple[list[TranslationCandidate], str]:
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
        img = _read_image_bytes(page.image.path)
        user_msg = (f"Source language: {page.source_lang}\nTarget language: {self._target_lang}\n"
                    "Extract all text bubbles and translate them.")
        msgs = [{"role": "system", "content": _DIRECT_SYS}, {"role": "user", "content": user_msg}]
        result = self.vision_structured(msgs, [img], schema=_DIRECT_TRANSLATE_SCHEMA)
        translations = [_item_to_candidate(item) for item in result.get("translations", [])]
        return translations, store.write_translations(page.page_id, translations)


def _read_image_bytes(path: str) -> bytes:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    return p.read_bytes()

def _item_to_bubble(item: dict) -> Bubble:
    b = item.get("bbox", {})
    return Bubble(bubble_id=item.get("bubble_id", ""),
        bbox=BoundingBox(x=float(b.get("x", 0)), y=float(b.get("y", 0)),
                         width=float(b.get("width", 0)), height=float(b.get("height", 0))),
        source_text=item.get("source_text", ""), reading_order=int(item.get("reading_order", 0)),
        speaker_name=item.get("speaker_name"), tone=item.get("tone"), notes=item.get("notes"))

def _item_to_candidate(item: dict) -> TranslationCandidate:
    return TranslationCandidate(bubble_id=item.get("bubble_id", ""), text=item.get("text", ""),
        rationale=item.get("rationale", ""), confidence=float(item.get("confidence", 0.0)))

def _parse_json_response(text: str) -> Dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    logger.warning("Failed to parse JSON from Ollama response, returning raw text")
    return {"raw": text}
