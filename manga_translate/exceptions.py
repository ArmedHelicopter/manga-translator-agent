"""Compatibility shim for mga.exceptions."""

from mga.exceptions import *  # noqa: F401,F403
from mga.exceptions import (  # explicit re-exports for clarity
    ConfigError,
    MangaTranslateError,
    ProviderError,
    ProviderResponseError,
    ProviderTimeoutError,
    RenderFallbackError,
    SchemaValidationError,
    StageExecutionError,
)

__all__ = [
    "ConfigError",
    "MangaTranslateError",
    "ProviderError",
    "ProviderResponseError",
    "ProviderTimeoutError",
    "RenderFallbackError",
    "SchemaValidationError",
    "StageExecutionError",
]
