"""llama.cpp provider (OpenAI-compatible llama-server API)."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from ..exceptions import ProviderResponseError
from .base import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://localhost:8080/v1"
DEFAULT_MODEL = "local-model"


def _parse_json(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("```")).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(f"Failed to parse JSON from llama.cpp response: {exc}") from exc


def _content(response: Any) -> str:
    c = response.choices[0].message.content
    if c is None:
        raise ProviderResponseError("llama.cpp returned empty content")
    return c


class LlamaCppProvider(LLMProvider):
    """llama.cpp server provider via OpenAI-compatible API (text only)."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        api_key: str = "no-key",
        temperature: float = 0.2,
    ) -> None:
        import openai

        self._model = model
        self._temperature = temperature
        self._client = openai.OpenAI(api_key=api_key, base_url=base_url)

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def supports_vision(self) -> bool:
        return False

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
        raise NotImplementedError("llama.cpp does not support vision input")

    def vision_structured(self, messages: List[Dict[str, Any]], images: List[bytes], schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        raise NotImplementedError("llama.cpp does not support vision input")
