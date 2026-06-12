"""Groq provider - fast inference LLM gateway."""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Dict, List, Optional

from ..exceptions import ProviderError, ProviderResponseError
from .base import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"

# Vision-capable models on Groq
VISION_MODELS: set[str] = set()  # Groq currently does not support vision


def _parse_json(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("```")).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(f"Failed to parse JSON from Groq response: {exc}") from exc


def _content(response: Any) -> str:
    c = response.choices[0].message.content
    if c is None:
        raise ProviderResponseError("Groq returned empty content")
    return c


def _usage(response: Any) -> dict[str, int]:
    u = getattr(response, "usage", None)
    if u is None:
        return {}
    return {
        "prompt_tokens": getattr(u, "prompt_tokens", 0),
        "completion_tokens": getattr(u, "completion_tokens", 0),
        "total_tokens": getattr(u, "total_tokens", 0),
    }


class GroqProvider(LLMProvider):
    """Groq provider using the OpenAI-compatible API.

    Groq offers extremely fast inference for text models.
    Does not support vision (use for translation/QA only).
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_key_env: str | None = None,
        base_url: str | None = None,
        base_url_env: str | None = None,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 8192,
        max_retries: int = 2,
    ) -> None:
        resolved_api_key = api_key
        if resolved_api_key is None and api_key_env:
            resolved_api_key = os.getenv(api_key_env)

        resolved_base_url = base_url
        if resolved_base_url is None and base_url_env:
            resolved_base_url = os.getenv(base_url_env)

        self._model = model or DEFAULT_MODEL
        self._temperature = temperature
        self._max_tokens = max_tokens

        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "OpenAI SDK not installed. Install with: pip install openai"
            ) from None

        self._client = OpenAI(
            api_key=resolved_api_key,
            base_url=resolved_base_url or DEFAULT_BASE_URL,
            max_retries=max_retries,
        )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def supports_vision(self) -> bool:
        # Groq does not support vision models at this time
        return False

    @property
    def cost_per_1k_tokens(self) -> Optional[float]:
        # Groq pricing (very competitive)
        costs = {
            "llama-3.3-70b-versatile": 0.00059,
            "llama-3.1-8b-instant": 0.00005,
            "mixtral-8x7b-32768": 0.00024,
            "gemma2-9b-it": 0.00020,
        }
        return costs.get(self._model.lower())

    # -- LLMProvider interface --------------------------------------------

    def chat(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=kwargs.pop("temperature", self._temperature),
            max_tokens=kwargs.pop("max_tokens", self._max_tokens),
            **kwargs,
        )
        return _content(resp)

    def chat_structured(self, messages: List[Dict[str, Any]], schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        resp = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=kwargs.pop("temperature", self._temperature),
            max_tokens=kwargs.pop("max_tokens", self._max_tokens),
            **kwargs,
        )
        return _parse_json(_content(resp))

    def vision(self, messages: List[Dict[str, Any]], images: List[bytes], **kwargs: Any) -> str:
        raise ProviderError("Groq does not support vision models. Use for translation/QA only.")

    def vision_structured(self, messages: List[Dict[str, Any]], images: List[bytes], schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        raise ProviderError("Groq does not support vision models. Use for translation/QA only.")