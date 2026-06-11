"""7-stage pipeline orchestration for manga translation."""

from __future__ import annotations

from .orchestrator import PipelineOrchestrator
from .stages import PipelineContext, PipelineStage
from .context import (
    TranslationContext,
    MemoryContext,
    CulturalContext,
    QAContext,
    ArtifactContext,
)

__all__ = [
    "PipelineOrchestrator",
    "PipelineStage",
    "PipelineContext",
    # Structured sub-contexts (new)
    "TranslationContext",
    "MemoryContext",
    "CulturalContext",
    "QAContext",
    "ArtifactContext",
]