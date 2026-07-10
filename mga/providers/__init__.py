"""Provider architecture for LLM integrations."""

from .base import LLMProvider
from .legacy import LLMProvider as LegacyLLMProvider

__all__ = [
    "LLMProvider",
    "LegacyLLMProvider",
    "get_provider",
    "select_provider",
    "OpenAIProvider",
    "AnthropicProvider",
    "GeminiProvider",
    "DeepSeekProvider",
    "OllamaProvider",
    "VLLMProvider",
    "OpenRouterProvider",
    "LMStudioProvider",
    "LlamaCppProvider",
]


def get_provider(name: str, **kwargs) -> LLMProvider:
    """Get a provider instance by name."""
    from .registry import get_provider as _get
    return _get(name, **kwargs)


def select_provider(stage: str, config: dict, force_local: bool = False) -> LLMProvider:
    """Select provider for a stage with fallback cascade."""
    from .registry import select_provider as _select
    return _select(stage, config, force_local=force_local)
