"""Provider registry with fallback cascade."""

from __future__ import annotations

from typing import Any

from ..exceptions import ProviderError
from .base import LLMProvider

_PROVIDER_MAP: dict[str, tuple[str, str]] = {
    "openai": (".openai_provider", "OpenAIProvider"),
    "anthropic": (".anthropic_provider", "AnthropicProvider"),
    "gemini": (".gemini_provider", "GeminiProvider"),
    "deepseek": (".deepseek_provider", "DeepSeekProvider"),
    "ollama": (".ollama_provider", "OllamaProvider"),
    "lmstudio": (".vllm_provider", "VLLMProvider"),
    "vllm": (".vllm_provider", "VLLMProvider"),
    "openrouter": (".openrouter_provider", "OpenRouterProvider"),
}


def _load_provider_class(name: str) -> type[LLMProvider]:
    entry = _PROVIDER_MAP.get(name.lower())
    if entry is None:
        raise ProviderError(f"Unknown provider: {name!r}")
    module_path, class_name = entry
    import importlib
    module = importlib.import_module(module_path, package=__package__)
    return getattr(module, class_name)


def get_provider(name: str, **kwargs: Any) -> LLMProvider:
    """Instantiate a provider by name."""
    cls = _load_provider_class(name)
    return cls(**kwargs)


def select_provider(
    stage: str,
    config: dict[str, Any],
    force_local: bool = False,
) -> LLMProvider:
    """Select provider for a stage with primary -> fallback -> local cascade.

    ``config`` should have the shape::

        {
            "stages": {"vision": {"primary": "openai", "fallback": "gemini", "local": "ollama"}},
            "providers": {"openai": {"api_key": "...", ...}},
        }
    """
    stages = config.get("stages", {})
    providers = config.get("providers", {})
    stage_config = stages.get(stage, {})

    if force_local:
        name = stage_config.get("local")
        if not name:
            raise ProviderError(f"No local provider configured for stage {stage!r}")
        return get_provider(name, **providers.get(name, {}))

    for key in ("primary", "fallback", "local"):
        name = stage_config.get(key)
        if name:
            try:
                return get_provider(name, **providers.get(name, {}))
            except Exception:
                continue

    raise ProviderError(f"No provider available for stage {stage!r}")
