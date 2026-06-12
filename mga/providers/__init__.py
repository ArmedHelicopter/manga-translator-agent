"""Provider layer - unified factory + cascade.

Single source of truth for all provider creation.
"""

from .factory import (
    # Factory functions
    create_provider,
    get_provider,
    resolve_provider_settings,
    get_default_model,
    get_provider_info,
    list_providers,
    list_profiles,
    list_all_providers,
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
    "get_provider_info",
    "list_providers",
    "list_profiles",
    "list_all_providers",
    "ProviderCascade",
    "ProviderCandidate",
    "ProviderCascadeAdapter",
    "LLMProvider",
]