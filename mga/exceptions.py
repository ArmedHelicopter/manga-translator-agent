"""Domain exceptions for the manga translation pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .pipeline.stages import PipelineContext


class MangaTranslateError(Exception):
    """Base exception for all domain-specific failures."""


class ConfigError(MangaTranslateError):
    """Raised when project or provider configuration is invalid."""


class ProviderError(MangaTranslateError):
    """Base exception for provider-layer failures."""


class ProviderTimeoutError(ProviderError):
    """Raised when a provider request exceeds the allowed timeout."""


class ProviderResponseError(ProviderError):
    """Raised when a provider returns malformed or unusable output."""


class SchemaValidationError(MangaTranslateError):
    """Raised when external data cannot be validated into internal schemas."""


class StageExecutionError(MangaTranslateError):
    """Raised when a pipeline stage cannot complete successfully."""


class RenderFallbackError(StageExecutionError):
    """Raised when rendering cannot complete and no fallback path succeeds."""


class RestartPipelineSignal(MangaTranslateError):
    """Control-flow signal: abort current run and restart from the beginning."""

    def __init__(
        self,
        reason: str = "",
        new_ocr_model: str | None = None,
        context_checkpoint: Any = None,
    ):
        super().__init__(reason)
        self.new_ocr_model = new_ocr_model
        self.context_checkpoint = context_checkpoint
