"""Mistral AI provider."""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any, Dict, List, Optional

from ..exceptions import ProviderError, ProviderResponseError
from .base import LLMProvider

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.mistral.ai/v1"
DEFAULT_MODEL = "mistral-large-latest"

# Vision-capable models
VISION_MODELS = {
    "mistral-large-latest",
    "mistral-large-3-2506",
    "mistral-nemo",
    "pixtral-large-latest",
    "pixtral-12b-2409",
}


def _parse_json(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("```")).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(f"Failed to parse JSON from Mistral response: {exc}") from exc


def _content(response: Any) -> str:
    if hasattr(response, "choices") and response.choices:
        choice = response.choices[0]
        if hasattr(choice, "message") and choice.message:
            content = choice.message.content
            if isinstance(content, list):
                return content[0].text if content else ""
            return content or ""
    if hasattr(response, "text") and response.text:
        return response.text
    raise ProviderResponseError("Mistral returned empty content")


def _usage(response: Any) -> dict[str, int]:
    u = getattr(response, "usage", None)
    if u is None:
        return {}
    return {
        "prompt_tokens": getattr(u, "prompt_tokens", 0),
        "completion_tokens": getattr(u, "completion_tokens", 0),
        "total_tokens": getattr(u, "total_tokens", 0),
    }


def _make_image_parts(images: List[bytes]) -> list[dict[str, Any]]:
    return [{
        "type": "image_url",
        "image_url": {"url": f"data:image/png;base64,{base64.standard_b64encode(i).decode('ascii')}"},
    } for i in images]


def _inject_images(messages: List[Dict[str, Any]], image_parts: list[dict[str, Any]]) -> List[Dict[str, Any]]:
    result = [dict(m) for m in messages]
    if result and result[-1].get("role") == "user":
        existing = result[-1].get("content", "")
        if isinstance(existing, str):
            result[-1]["content"] = [{"type": "text", "text": existing}, *image_parts]
        elif isinstance(existing, list):
            existing.extend(image_parts)
    return result


class MistralProvider(LLMProvider):
    """Mistral AI provider using the OpenAI-compatible API.

    Supports vision for pixtral and mistral-large models.
    Uses JSON mode for structured output.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_key_env: str | None = None,
        base_url: str | None = None,
        base_url_env: str | None = None,
        model: str | None = None,
        vision_model: str | None = None,
        text_model: str | None = None,
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

        self._vision_model = vision_model or model or DEFAULT_MODEL
        self._text_model = text_model or model or "mistral-small-latest"
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
        return self._vision_model

    @property
    def supports_vision(self) -> bool:
        return self._vision_model.lower() in VISION_MODELS

    @property
    def cost_per_1k_tokens(self) -> Optional[float]:
        costs = {
            "mistral-large-latest": 0.002,
            "mistral-large-3-2506": 0.002,
            "mistral-small-latest": 0.00015,
            "mistral-nemo": 0.00015,
            "pixtral-large-latest": 0.002,
            "pixtral-12b-2409": 0.00015,
        }
        return costs.get(self._vision_model.lower())

    # -- LLMProvider interface --------------------------------------------

    def chat(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        resp = self._client.chat.completions.create(
            model=self._text_model,
            messages=messages,
            temperature=kwargs.pop("temperature", self._temperature),
            max_tokens=kwargs.pop("max_tokens", self._max_tokens),
            **kwargs,
        )
        return _content(resp)

    def chat_structured(self, messages: List[Dict[str, Any]], schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        resp = self._client.chat.completions.create(
            model=self._text_model,
            messages=messages,
            response_format={"type": "json_object"},
            temperature=kwargs.pop("temperature", self._temperature),
            max_tokens=kwargs.pop("max_tokens", self._max_tokens),
            **kwargs,
        )
        return _parse_json(_content(resp))

    def vision(self, messages: List[Dict[str, Any]], images: List[bytes], **kwargs: Any) -> str:
        resp = self._client.chat.completions.create(
            model=self._vision_model,
            messages=_inject_images(messages, _make_image_parts(images)),
            temperature=kwargs.pop("temperature", self._temperature),
            max_tokens=kwargs.pop("max_tokens", self._max_tokens),
            **kwargs,
        )
        return _content(resp)

    def vision_structured(self, messages: List[Dict[str, Any]], images: List[bytes], schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        resp = self._client.chat.completions.create(
            model=self._vision_model,
            messages=_inject_images(messages, _make_image_parts(images)),
            response_format={"type": "json_object"},
            temperature=kwargs.pop("temperature", self._temperature),
            max_tokens=kwargs.pop("max_tokens", self._max_tokens),
            **kwargs,
        )
        return _parse_json(_content(resp))