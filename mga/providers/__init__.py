"""Provider layer - unified factory + cascade.

Single source of truth for all provider creation.
"""

from .factory import (
    # Factory functions
    create_provider,
    get_provider,
    resolve_provider_settings,
    get_default_model,
    list_providers,
    list_profiles,
    # Base
    LLMProvider,
)
from .cascade import (
    # Cascade
    ProviderCascade,
    ProviderCandidate,
    ProviderCascadeAdapter,
)

__all__ = [
    "create_provider",
    "get_provider",
    "resolve_provider_settings",
    "get_default_model",
    "list_providers",
    "list_profiles",
    "ProviderCascade",
    "ProviderCandidate",
    "ProviderCascadeAdapter",
    "LLMProvider",
]