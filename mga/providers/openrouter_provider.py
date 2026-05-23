"""OpenRouter provider — unified gateway to multiple LLM APIs."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, List

from ..exceptions import ProviderError, ProviderResponseError
from .base import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-4o-mini"


def _parse_json(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("```")).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(f"Failed to parse JSON from OpenRouter response: {exc}") from exc


def _content(response: Any) -> str:
    c = response.choices[0].message.content
    if c is None:
        raise ProviderResponseError("OpenRouter returned empty content")
    return c


def _usage(response: Any) -> dict[str, int]:
    u = getattr(response, "usage", None)
    if u is None:
        return {}
    return {"prompt_tokens": getattr(u, "prompt_tokens", 0),
            "completion_tokens": getattr(u, "completion_tokens", 0),
            "total_tokens": getattr(u, "total_tokens", 0)}


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


class OpenRouterProvider(LLMProvider):
    """Unified LLM gateway via OpenRouter (OpenAI-compatible API)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_retries: int = 2,
    ) -> None:
        import openai

        self._model = model or DEFAULT_MODEL
        self._temperature = temperature
        self._client = openai.OpenAI(
            api_key=api_key,
            base_url=base_url or DEFAULT_BASE_URL,
            max_retries=max_retries,
        )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def supports_vision(self) -> bool:
        return "gpt-4o" in self._model or "claude" in self._model or "gemini" in self._model

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
