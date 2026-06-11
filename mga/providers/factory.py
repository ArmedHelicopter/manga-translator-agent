"""Unified provider factory - single source of truth for provider creation.

This module consolidates all provider creation logic from:
- registry.py (legacy, deprecated)
- factory.py (new, now canonical)

The cascade logic is in cascade.py.
"""

from __future__ import annotations

import importlib
from typing import Any

from ..exceptions import ProviderError

# ── Provider Registry ───────────────────────────────────────────────────────────

_PROVIDER_MAP: dict[str, tuple[str, str]] = {
    "openai": (".openai_provider", "OpenAIProvider"),
    "anthropic": (".anthropic_provider", "AnthropicProvider"),
    "gemini": (".gemini_provider", "GeminiProvider"),
    "deepseek": (".deepseek_provider", "DeepSeekProvider"),
    "ollama": (".ollama_provider", "OllamaProvider"),
    "lmstudio": (".lmstudio_provider", "LMStudioProvider"),
    "vllm": (".vllm_provider", "VLLMProvider"),
    "openrouter": (".openrouter_provider", "OpenRouterProvider"),
    "llamacpp": (".llamacpp_provider", "LlamaCppProvider"),
}

# Provider profiles with default settings
_PROVIDER_PROFILES: dict[str, dict[str, Any]] = {
    "mimo": {
        "provider_type": "openai",
        "api_key_env": "MIMO_API_KEY",
        "base_url_env": "MIMO_BASE_URL",
        "base_url": "https://token-plan-cn.xiaomimimo.com/v1",
        "vision_model": "mimo-v2.5",
        "text_model": "mimo-v2.5-pro",
    },
}


def _load_provider_class(name: str) -> type:
    """Load provider class by name."""
    entry = _PROVIDER_MAP.get(name.lower())
    if entry is None:
        raise ProviderError(f"Unknown provider: {name!r}")
    module_path, class_name = entry
    module = importlib.import_module(module_path, package=__package__)
    return getattr(module, class_name)


def resolve_provider_settings(name: str, settings: dict[str, Any] | None = None) -> tuple[str, dict[str, Any]]:
    """Resolve provider name to concrete type and kwargs.

    Args:
        name: Provider name (openai, anthropic, mimo, etc.)
        settings: Optional settings dict

    Returns:
        (provider_type, resolved_settings) tuple
    """
    provider_name = name.lower()
    resolved = dict(settings or {})

    # Merge with profile if exists
    profile = _PROVIDER_PROFILES.get(provider_name)
    if profile:
        merged = dict(profile)
        merged.update(resolved)
        resolved = merged

    provider_type = str(resolved.pop("provider_type", provider_name)).lower()
    return provider_type, resolved


def create_provider(name: str, settings: dict[str, Any] | None = None, **kwargs: Any):
    """Create a provider instance by name.

    Args:
        name: Provider name (openai, anthropic, mimo, etc.)
        settings: Optional settings dict
        **kwargs: Additional settings as keyword arguments

    Returns:
        LLMProvider instance
    """
    merged = dict(settings or {})
    merged.update(kwargs)

    provider_type, resolved = resolve_provider_settings(name, merged)

    # Check for plugin provider first
    if provider_type not in _PROVIDER_MAP:
        from mga.plugins import has_plugin_class, instantiate_plugin_from_settings
        if has_plugin_class(resolved):
            return instantiate_plugin_from_settings(resolved)

    cls = _load_provider_class(provider_type)
    return cls(**resolved)


def get_provider(name: str, **kwargs: Any):
    """Backward-compatible alias for create_provider."""
    return create_provider(name, kwargs)


def get_default_model(provider: str, stage: str | None = None) -> str:
    """Get default model for a provider and stage.

    Args:
        provider: Provider name
        stage: Optional stage (vision, translation, qa)

    Returns:
        Model name string
    """
    profile = _PROVIDER_PROFILES.get(provider.lower(), {})
    if stage == "vision":
        return str(profile.get("vision_model") or profile.get("model") or "")
    if stage in ("translation", "translate", "qa"):
        return str(profile.get("text_model") or profile.get("translate_model") or profile.get("model") or "")
    return str(profile.get("model") or profile.get("vision_model") or profile.get("text_model") or "")


def list_providers() -> list[str]:
    """List all registered provider names."""
    return list(_PROVIDER_MAP.keys())


def list_profiles() -> list[str]:
    """List all provider profile names."""
    return list(_PROVIDER_PROFILES.keys())


# ── Re-export for convenience ──────────────────────────────────────────────────

from .base import LLMProvider

__all__ = [
    "create_provider",
    "get_provider",
    "resolve_provider_settings",
    "get_default_model",
    "list_providers",
    "list_profiles",
    "LLMProvider",
]