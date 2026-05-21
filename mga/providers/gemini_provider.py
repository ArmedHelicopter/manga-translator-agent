"""Google Gemini LLM provider."""

from __future__ import annotations

import json
from io import BytesIO
from typing import Any, Dict, List, Optional

from PIL import Image

from ..artifacts.store import ArtifactStore
from ..models import BoundingBox, Bubble, Page, TranslationCandidate, Utterance
from .base import LLMProvider


class GeminiProvider(LLMProvider):
    """Google Gemini provider using the google-generativeai SDK."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash") -> None:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._model_name = model
        self._genai = genai

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def supports_vision(self) -> bool:
        return True

    @property
    def cost_per_1k_tokens(self) -> Optional[float]:
        return None

    # -- Helpers -----------------------------------------------------------

    def _get_model(self, *, json_mode: bool = False):  # type: ignore[no-untyped-def]
        if json_mode:
            return self._genai.GenerativeModel(
                self._model_name,
                generation_config=self._genai.GenerationConfig(
                    response_mime_type="application/json",
                ),
            )
        return self._genai.GenerativeModel(self._model_name)

    @staticmethod
    def _encode_image(data: bytes) -> Dict[str, Any]:
        return {"inline_data": {"mime_type": "image/png", "data": data}}

    @staticmethod
    def _bytes_from_image(image: Image.Image) -> bytes:
        buf = BytesIO()
        image.save(buf, format="PNG")
        return buf.getvalue()

    def _to_parts(
        self, messages: List[Dict[str, Any]], images: Optional[List[bytes]] = None
    ) -> List[Any]:
        parts: List[Any] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                parts.append(f"[System] {content}")
            else:
                parts.append(content)
        for img_bytes in (images or []):
            parts.append(self._encode_image(img_bytes))
        return parts

    @staticmethod
    def _safe_json(text: str) -> Dict[str, Any]:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw": text}

    # -- LLMProvider interface --------------------------------------------

    def chat(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        model = self._get_model()
        response = model.generate_content(self._to_parts(messages))
        return response.text or ""

    def chat_structured(
        self, messages: List[Dict[str, Any]], schema: Dict[str, Any], **kwargs: Any,
    ) -> Dict[str, Any]:
        model = self._get_model(json_mode=True)
        response = model.generate_content(self._to_parts(messages))
        return self._safe_json(response.text or "{}")

    def vision(
        self, messages: List[Dict[str, Any]], images: List[bytes], **kwargs: Any,
    ) -> str:
        model = self._get_model()
        response = model.generate_content(self._to_parts(messages, images=images))
        return response.text or ""

    def vision_structured(
        self, messages: List[Dict[str, Any]], images: List[bytes],
        schema: Dict[str, Any], **kwargs: Any,
    ) -> Dict[str, Any]:
        model = self._get_model(json_mode=True)
        response = model.generate_content(self._to_parts(messages, images=images))
        return self._safe_json(response.text or "{}")

    # -- Benchmark helpers -------------------------------------------------

    def vision_extract(self, page: Page, store: ArtifactStore) -> List[Bubble]:
        """Use vision to extract text and bounding boxes from a page image."""
        img_bytes: List[bytes] = []
        if page.image.path:
            img_bytes.append(self._bytes_from_image(Image.open(page.image.path)))

        prompt = (
            "You are an OCR and layout analysis system for manga.\n"
            "Given the page image, extract every speech bubble.\n"
            "Return a JSON array of objects, each with:\n"
            '  "bbox": {"x", "y", "width", "height"} (floats 0-1 normalized),\n'
            '  "text": the transcribed text,\n'
            '  "speaker": optional speaker name,\n'
            '  "reading_order": int starting from 0.\n'
            "Return only the JSON array."
        )
        raw = self.vision([{"role": "user", "content": prompt}], images=img_bytes)
        data = self._safe_json(raw)
        items = data if isinstance(data, list) else data.get("bubbles", [])

        bubbles: List[Bubble] = []
        for idx, item in enumerate(items):
            bbox = item.get("bbox", {})
            bubbles.append(Bubble(
                bubble_id=f"{page.page_id}_b{idx}",
                bbox=BoundingBox(
                    x=float(bbox.get("x", 0)), y=float(bbox.get("y", 0)),
                    width=float(bbox.get("width", 0)), height=float(bbox.get("height", 0)),
                ),
                source_text=item.get("text", ""),
                reading_order=int(item.get("reading_order", idx)),
                speaker_name=item.get("speaker"),
            ))
        store.write_page(page.page_id, {"bubbles": [b.model_dump() for b in bubbles]})
        return bubbles

    def translate(
        self, page: Page, utterances: List[Utterance], store: ArtifactStore,
        target_lang: str = "en",
    ) -> List[TranslationCandidate]:
        """Translate utterances using the LLM (no vision)."""
        entries = []
        for u in utterances:
            entry = f"[{u.bubble_id}] {u.source_text}"
            if u.speaker:
                entry += f" (speaker: {u.speaker})"
            if u.tone:
                entry += f" (tone: {u.tone})"
            entries.append(entry)

        prompt = (
            f"Translate the following manga dialogue from Japanese to {target_lang}.\n"
            "Keep the translation natural and appropriate for manga.\n"
            "Return a JSON array of objects with:\n"
            '  "bubble_id": string,\n'
            '  "text": translated text,\n'
            '  "rationale": brief reason for translation choices,\n'
            '  "confidence": float 0-1.\n\n'
            "Dialogue entries:\n" + "\n".join(entries)
        )
        raw = self.chat([{"role": "user", "content": prompt}])
        data = self._safe_json(raw)
        items = data if isinstance(data, list) else data.get("translations", [])

        candidates: List[TranslationCandidate] = []
        for item in items:
            candidates.append(TranslationCandidate(
                bubble_id=item.get("bubble_id", ""),
                text=item.get("text", ""),
                rationale=item.get("rationale", ""),
                confidence=float(item.get("confidence", 0.0)),
            ))
        store.write_translations(page.page_id, [c.model_dump() for c in candidates])
        return candidates

    def direct_translate_page(
        self, page: Page, store: ArtifactStore, target_lang: str = "en",
    ) -> List[TranslationCandidate]:
        """Vision + translate in a single call -- send image, get translations."""
        img_bytes: List[bytes] = []
        if page.image.path:
            img_bytes.append(self._bytes_from_image(Image.open(page.image.path)))

        scene = f"\nScene context: {page.scene_summary}" if page.scene_summary else ""
        prompt = (
            "You are a professional manga translator.\n"
            f"Translate all Japanese text in this page to {target_lang}.{scene}\n"
            "For each speech bubble or text element, return a JSON array of:\n"
            '  {"bubble_id": "auto", "text": "translated text",\n'
            '   "rationale": "brief note", "confidence": 0.0-1.0}\n'
            "Order them by reading order (top-right to bottom-left for manga)."
        )
        raw = self.vision([{"role": "user", "content": prompt}], images=img_bytes)
        data = self._safe_json(raw)
        items = data if isinstance(data, list) else data.get("translations", [])

        candidates: List[TranslationCandidate] = []
        for idx, item in enumerate(items):
            candidates.append(TranslationCandidate(
                bubble_id=item.get("bubble_id", f"{page.page_id}_t{idx}"),
                text=item.get("text", ""),
                rationale=item.get("rationale", ""),
                confidence=float(item.get("confidence", 0.0)),
            ))
        store.write_translations(page.page_id, [c.model_dump() for c in candidates])
        return candidates
