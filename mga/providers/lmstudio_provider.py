"""LM Studio provider (OpenAI-compatible local API)."""

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..exceptions import ProviderResponseError
from .base import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:1234/v1"
DEFAULT_MODEL = "local-model"


def _parse_json(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("```")).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(f"Failed to parse JSON from LM Studio response: {exc}") from exc


def _content(response: Any) -> str:
    c = response.choices[0].message.content
    if c is None:
        raise ProviderResponseError("LM Studio returned empty content")
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


class LMStudioProvider(LLMProvider):
    """LM Studio local server provider (OpenAI-compatible API)."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        api_key: str = "lm-studio",
        temperature: float = 0.2,
        vision_enabled: bool = True,
    ) -> None:
        import openai

        self._model = model
        self._temperature = temperature
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

    def chat(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        resp = self._client.chat.completions.create(
            model=self._model, messages=messages,
            temperature=kwargs.pop("temperature", self._temperature), **kwargs,
        )
        return _content(resp)

    def chat_structured(self, messages: List[Dict[str, Any]], schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        resp = self._client.chat.completions.create(
            model=self._model, messages=messages,
            response_format={"type": "json_object"},
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
