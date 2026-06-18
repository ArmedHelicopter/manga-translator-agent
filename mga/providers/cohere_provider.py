"""Cohere LLM provider with vision support."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict, List, Optional

from ..exceptions import ProviderError, ProviderResponseError
from .base import LLMProvider

logger = logging.getLogger(__name__)

# Provider metadata for lazy discovery (see mga/providers/lazy_registry.py).
PROVIDER_METADATA = {
    "name": "cohere",
    "class": "CohereProvider",
    "vision": True,
    "structured": "json_mode",
    "notes": "Cohere Command A+ models, native SDK",
}

DEFAULT_BASE_URL = "https://api.cohere.ai"
DEFAULT_MODEL = "command-a-plus-128k"

# Vision-capable models
VISION_MODELS = {
    "command-r-plus-08-2024",
    "command-a-plus-128k",
    "command-a-plus",
    "cua-plus-latest",
    "cua-standard-latest",
}


def _parse_json(raw: str) -> Any:
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(l for l in text.splitlines() if not l.strip().startswith("```")).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ProviderResponseError(f"Failed to parse JSON from Cohere response: {exc}") from exc


def _content(response: Any) -> str:
    if hasattr(response, "text") and response.text:
        return response.text
    if hasattr(response, "message") and response.message:
        content = response.message.content
        if isinstance(content, list) and content:
            return content[0].text if hasattr(content[0], "text") else str(content[0])
        return str(content)
    raise ProviderResponseError("Cohere returned empty content")


def _usage(response: Any) -> dict[str, int]:
    return {
        "prompt_tokens": getattr(response, "prompt_tokens", 0),
        "completion_tokens": getattr(response, "completion_tokens", 0),
        "total_tokens": getattr(response, "total_tokens", 0),
    }


def _encode_image(image_bytes: bytes) -> str:
    return base64.standard_b64encode(image_bytes).decode("ascii")


def _inject_images(messages: List[Dict[str, Any]], images: List[bytes]) -> List[Dict[str, Any]]:
    """Inject images into the last user message as base64."""
    result = [dict(m) for m in messages]
    if result and result[-1].get("role") == "user":
        existing = result[-1].get("content", "")
        if isinstance(existing, str):
            image_parts = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _encode_image(img)}} for img in images]
            result[-1]["content"] = [{"type": "text", "text": existing}] + image_parts
        elif isinstance(existing, list):
            for img in images:
                existing.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": _encode_image(img)}})
    return result


class CohereProvider(LLMProvider):
    """Cohere provider using the Chat API with multimodal support.

    Supports vision for multimodal models (Command A+, Command R+).
    Uses JSON mode for structured output.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        api_key_env: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        vision_model: str | None = None,
        text_model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        max_retries: int = 2,
    ) -> None:
        import os

        resolved_api_key = api_key
        if resolved_api_key is None and api_key_env:
            resolved_api_key = os.getenv(api_key_env)

        self._vision_model = vision_model or model or DEFAULT_MODEL
        self._text_model = text_model or model or DEFAULT_MODEL
        self._temperature = temperature
        self._max_tokens = max_tokens

        try:
            import cohere
        except ImportError:
            raise ImportError(
                "Cohere SDK not installed. Install with: pip install cohere"
            ) from None

        self._client = cohere.Client(
            api_key=resolved_api_key,
            base_url=base_url,
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
            "command-a-plus-128k": 0.003,
            "command-r-plus-08-2024": 0.003,
            "command-r-8b-07-2024": 0.0005,
            "command-r-4b-07-2024": 0.0003,
        }
        return costs.get(self._vision_model.lower())

    # -- LLMProvider interface --------------------------------------------

    def chat(self, messages: List[Dict[str, Any]], **kwargs: Any) -> str:
        chat_messages = self._format_messages(messages)
        response = self._client.chat(
            model=self._text_model,
            message=chat_messages[-1]["content"] if chat_messages else "",
            chat_history=chat_messages[:-1] if len(chat_messages) > 1 else None,
            temperature=kwargs.pop("temperature", self._temperature),
            max_tokens=kwargs.pop("max_tokens", self._max_tokens),
            **kwargs,
        )
        return _content(response)

    def chat_structured(self, messages: List[Dict[str, Any]], schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        chat_messages = self._format_messages(messages)
        # Cohere uses preamble for system instructions
        preamble = ""
        for msg in messages:
            if msg.get("role") == "system":
                preamble = msg["content"]
                break

        response = self._client.chat(
            model=self._text_model,
            message=chat_messages[-1]["content"] if chat_messages else "",
            chat_history=chat_messages[:-1] if len(chat_messages) > 1 else None,
            preamble=preamble if preamble else None,
            temperature=kwargs.pop("temperature", self._temperature),
            max_tokens=kwargs.pop("max_tokens", self._max_tokens),
            response_format={"type": "json_object", "json_schema": schema},
            **kwargs,
        )
        return _parse_json(_content(response))

    def vision(self, messages: List[Dict[str, Any]], images: List[bytes], **kwargs: Any) -> str:
        if not self.supports_vision:
            raise ProviderError(f"Model {self._vision_model} does not support vision")

        formatted = self._format_messages_vision(messages, images)
        response = self._client.chat(
            model=self._vision_model,
            message=formatted["message"],
            documents=formatted.get("documents"),
            tools=formatted.get("tools"),
            temperature=kwargs.pop("temperature", self._temperature),
            max_tokens=kwargs.pop("max_tokens", self._max_tokens),
            **kwargs,
        )
        return _content(response)

    def vision_structured(self, messages: List[Dict[str, Any]], images: List[bytes], schema: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        if not self.supports_vision:
            raise ProviderError(f"Model {self._vision_model} does not support vision")

        formatted = self._format_messages_vision(messages, images)
        preamble = ""
        for msg in messages:
            if msg.get("role") == "system":
                preamble = msg["content"]
                break

        response = self._client.chat(
            model=self._vision_model,
            message=formatted["message"],
            chat_history=formatted.get("chat_history"),
            preamble=preamble if preamble else None,
            temperature=kwargs.pop("temperature", self._temperature),
            max_tokens=kwargs.pop("max_tokens", self._max_tokens),
            response_format={"type": "json_object", "json_schema": schema},
            **kwargs,
        )
        return _parse_json(_content(response))

    # -- Helpers ---------------------------------------------------------

    def _format_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format messages for Cohere chat API."""
        formatted = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                continue  # System goes in preamble
            content = msg.get("content", "")
            if isinstance(content, list):
                # Extract text from mixed content
                text_parts = []
                for part in content:
                    if isinstance(part, dict):
                        if part.get("type") == "text":
                            text_parts.append(part["text"])
                    else:
                        text_parts.append(str(part))
                content = " ".join(text_parts)
            formatted.append({"role": role, "content": content})
        return formatted

    def _format_messages_vision(
        self,
        messages: List[Dict[str, Any]],
        images: List[bytes],
    ) -> Dict[str, Any]:
        """Format messages with images for Cohere multimodal API."""
        result = {
            "message": "",
            "chat_history": [],
        }

        user_content = []
        for msg in messages:
            role = msg.get("role", "user")
            if role == "system":
                continue
            content = msg.get("content", "")
            if isinstance(content, list):
                user_content.extend(content)
            else:
                user_content.append(content)

        # Add images to the last message
        for img in images:
            user_content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": _encode_image(img),
                },
            })

        # Extract text and set final message
        text_parts = []
        for part in user_content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    text_parts.append(part["text"])
            else:
                text_parts.append(str(part))

        result["message"] = " ".join(text_parts)
        return result