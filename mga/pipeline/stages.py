"""Base classes for the 7-stage translation pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from mga.models import Page, ProjectConfig, TranslationCandidate


class PipelineContext(BaseModel):
    """Mutable context passed between pipeline stages."""

    project_config: Any = None
    pages: list[Page] = Field(default_factory=list)
    current_page: Page | None = None
    translations: list[TranslationCandidate] = Field(default_factory=list)
    qa_report: dict = Field(default_factory=dict)
    cultural_context: dict = Field(default_factory=dict)
    memory_context: dict = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PipelineStage(ABC):
    """Abstract base class for a single pipeline stage."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this stage."""

    @property
    @abstractmethod
    def order(self) -> int:
        """Execution order (lower runs first)."""

    @abstractmethod
    def execute(self, context: PipelineContext) -> PipelineContext:
        """Run this stage and return the (possibly mutated) context."""
