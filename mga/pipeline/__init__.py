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
from .page_footnotes import (
    PageFootnoteService,
    get_page_footnote_service,
    detect_footnote_terms,
    CULTURAL_REFERENCES,
    FICTIONAL_REFERENCES,
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
    # Page footnotes
    "PageFootnoteService",
    "get_page_footnote_service",
    "detect_footnote_terms",
    "CULTURAL_REFERENCES",
    "FICTIONAL_REFERENCES",
]