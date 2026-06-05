"""MiMo OpenAI-compatible provider."""

from __future__ import annotations

import os

from .openai_provider import OpenAIProvider

MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
MIMO_MODEL = "mimo-v2.5-pro"


class MiMoProvider(OpenAIProvider):
    """Provider for Xiaomi MiMo's OpenAI-compatible chat API."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        translate_model: str | None = None,
        temperature: float = 0.2,
        max_retries: int = 2,
    ) -> None:
        super().__init__(
            api_key=api_key or os.getenv("MIMO_API_KEY"),
            base_url=base_url or os.getenv("MIMO_BASE_URL") or MIMO_BASE_URL,
            model=model or MIMO_MODEL,
            translate_model=translate_model or model or MIMO_MODEL,
            temperature=temperature,
            max_retries=max_retries,
        )
