"""Consolidated Provider Factory — single entry point for all LLM providers.

This module provides a unified interface to all 9 supported LLM providers:
- OpenAI (GPT-4o, GPT-4o-mini)
- Anthropic (Claude 3.5, Claude 3)
- Google Gemini
- DeepSeek
- OpenRouter (unified gateway)
- Ollama (local)
- vLLM (local OpenAI-compatible)
- LM Studio (local)
- llama.cpp (local)

Usage:
    from mga.core.provider_factory import create_provider, get_cascade

    # Create a single provider
    provider = create_provider("openai", {"api_key": "sk-..."})

    # Get a cascade for a stage
    cascade = get_cascade(config, "translation")
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from PIL.Image import Image

logger = logging.getLogger(__name__)


# === Provider Protocol ===

class LLMProvider(Protocol):
    """Protocol for all LLM providers."""

    provider_name: str
    model: str

    def chat(self, messages: list[dict], **kwargs) -> str:
        """Send chat completion request."""
        ...

    def vision(self, image: "Image", prompt: str, **kwargs) -> str:
        """Send vision request."""
        ...


# === Base Provider ===

class BaseProvider(ABC):
    """Abstract base for all providers."""

    provider_name: str = ""
    default_model: str = ""

    def __init__(self, api_key: str = "", model: str = "", **settings):
        self.api_key = api_key
        self.model = model or self.default_model
        self.settings = settings

    @abstractmethod
    def chat(self, messages: list[dict], **kwargs) -> str:
        """Send chat completion request."""
        ...

    def vision(self, image: "Image", prompt: str, **kwargs) -> str:
        """Send vision request. Override in providers that support it."""
        raise NotImplementedError(f"{self.provider_name} does not support vision")

    def get_vision_capability(self) -> tuple[bool, str]:
        """Check if provider supports vision."""
        try:
            self.vision(None, "test")
            return True, ""
        except NotImplementedError:
            return False, "Provider does not support vision"
        except Exception as exc:
            return False, str(exc)


# === Provider Registry ===

_PROVIDER_CLASSES: dict[str, type[BaseProvider]] = {}


def register_provider(name: str):
    """Decorator to register a provider class."""
    def decorator(cls: type[BaseProvider]):
        _PROVIDER_CLASSES[name] = cls
        return cls
    return decorator


def create_provider(name: str, settings: dict[str, Any] | None = None, **kwargs) -> LLMProvider:
    """Create a provider instance by name.

    Args:
        name: Provider name (e.g., "openai", "anthropic", "gemini")
        settings: Provider settings from config
        **kwargs: Additional settings merged with settings

    Returns:
        Provider instance implementing LLMProvider protocol
    """
    settings = settings or {}
    settings.update(kwargs)

    if name not in _PROVIDER_CLASSES:
        # Lazy import on first use
        _lazy_import_providers()
        if name not in _PROVIDER_CLASSES:
            raise ValueError(f"Unknown provider: {name}. Available: {list(_PROVIDER_CLASSES.keys())}")

    cls = _PROVIDER_CLASSES[name]
    return cls(**settings)


def _lazy_import_providers():
    """Lazy import all provider classes."""
    global _PROVIDER_CLASSES
    if _PROVIDER_CLASSES:
        return

    try:
        from .openai_provider import OpenAIProvider
        _PROVIDER_CLASSES["openai"] = OpenAIProvider
    except ImportError:
        pass

    try:
        from .anthropic_provider import AnthropicProvider
        _PROVIDER_CLASSES["anthropic"] = AnthropicProvider
    except ImportError:
        pass

    try:
        from .gemini_provider import GeminiProvider
        _PROVIDER_CLASSES["gemini"] = GeminiProvider
    except ImportError:
        pass

    try:
        from .deepseek_provider import DeepSeekProvider
        _PROVIDER_CLASSES["deepseek"] = DeepSeekProvider
    except ImportError:
        pass

    try:
        from .openrouter_provider import OpenRouterProvider
        _PROVIDER_CLASSES["openrouter"] = OpenRouterProvider
    except ImportError:
        pass

    try:
        from .ollama_provider import OllamaProvider
        _PROVIDER_CLASSES["ollama"] = OllamaProvider
    except ImportError:
        pass

    try:
        from .vllm_provider import VLLMProvider
        _PROVIDER_CLASSES["vllm"] = VLLMProvider
    except ImportError:
        pass

    try:
        from .lmstudio_provider import LMStudioProvider
        _PROVIDER_CLASSES["lmstudio"] = LMStudioProvider
    except ImportError:
        pass

    try:
        from .llamacpp_provider import LlamaCPPProvider
        _PROVIDER_CLASSES["llama.cpp"] = LlamaCPPProvider
    except ImportError:
        pass


def list_providers() -> list[str]:
    """List all registered provider names."""
    _lazy_import_providers()
    return list(_PROVIDER_CLASSES.keys())


def get_provider(name: str, **settings) -> LLMProvider:
    """Alias for create_provider for backwards compatibility."""
    return create_provider(name, settings)


# === Cascade Support ===

class ProviderCascade:
    """Cascade through providers with fallback logic."""

    def __init__(self, config: Any, stage: str = "translation"):
        self.config = config
        self.stage = stage
        self.providers: list[LLMProvider] = []
        self.errors: list[dict] = []
        self._load_cascade()

    def _load_cascade(self):
        """Load provider cascade from config."""
        routes = getattr(self.config, "provider_routes", {})
        stage_config = routes.get(self.stage)
        if not stage_config:
            return

        for role in ("primary", "fallback", "local"):
            route = getattr(stage_config, role, None)
            if not route:
                continue
            try:
                provider = create_provider(
                    route.provider,
                    self.config.provider_settings.get(route.provider, {}),
                )
                self.providers.append(provider)
            except Exception as exc:
                logger.debug("Failed to load provider %s: %s", route.provider, exc)
                self.errors.append({
                    "provider": route.provider,
                    "role": role,
                    "error": str(exc),
                })

    def call(self, messages: list[dict], **kwargs) -> str:
        """Call providers in cascade until success."""
        for provider in self.providers:
            try:
                return provider.chat(messages, **kwargs)
            except Exception as exc:
                logger.debug("Provider %s failed: %s", provider.provider_name, exc)
                self.errors.append({
                    "provider": provider.provider_name,
                    "error": str(exc),
                })
                continue
        raise RuntimeError(f"All providers failed for stage {self.stage}")

    @property
    def candidates(self) -> list[Any]:
        """Return provider candidates for capability checking."""
        return [
            type("Candidate", (), {
                "provider": p.provider_name,
                "model": getattr(p, "model", ""),
                "settings": {},
            })()
            for p in self.providers
        ]


__all__ = [
    "LLMProvider",
    "BaseProvider",
    "register_provider",
    "create_provider",
    "list_providers",
    "get_provider",
    "ProviderCascade",
]