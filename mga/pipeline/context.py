"""Structured context objects for the translation pipeline.

Replaces the monolithic god-object pattern with focused, single-responsibility
context objects that can be used independently or composed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from mga.models import Page, ProjectConfig, TranslationCandidate


class TranslationContext(BaseModel):
    """Translation-specific state: pages, translations, current page."""

    pages: list[Any] = Field(default_factory=list)
    current_page: Any | None = None
    translations: list[Any] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


class MemoryContext(BaseModel):
    """Memory system context: character profiles, page profiles, scene contexts."""

    character_profiles: dict[str, dict] = Field(default_factory=dict)
    page_profiles: dict[str, dict[str, dict]] = Field(default_factory=dict)
    scene_contexts: dict[str, dict] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


class CulturalContext(BaseModel):
    """Cultural adaptation context: per-page cultural annotations."""

    # {page_id: {bubble_id: cultural_notes}}
    annotations: dict[str, dict[str, dict]] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


class QAContext(BaseModel):
    """QA context: report and per-bubble QA results."""

    report: dict = Field(default_factory=dict)
    bubble_results: dict[str, dict[str, Any]] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


class ArtifactContext(BaseModel):
    """Artifact context: structured outputs and metadata."""

    artifacts: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        arbitrary_types_allowed = True


class PipelineContext(BaseModel):
    """Mutable context passed between pipeline stages.

    Composed of focused sub-contexts for structured data, with direct dict
    fields for legacy compatibility.
    """

    project_config: Any = None

    # Structured sub-contexts (new architecture)
    translation: TranslationContext = Field(default_factory=TranslationContext)
    memory: MemoryContext = Field(default_factory=MemoryContext)
    cultural: CulturalContext = Field(default_factory=CulturalContext)
    qa: QAContext = Field(default_factory=QAContext)

    # Direct dict fields for compatibility
    artifacts: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    errors: list[dict] = Field(default_factory=list)
    ocr_guard_state: dict[str, Any] = Field(default_factory=dict)

    # Legacy alias support - allows gradual migration
    pages: list[Any] = Field(default_factory=list)
    current_page: Any | None = None
    translations: list[Any] = Field(default_factory=list)
    qa_report: dict = Field(default_factory=dict)
    cultural_context: dict = Field(default_factory=dict)
    memory_context: dict = Field(default_factory=dict)

    # Pipeline infrastructure (excluded from serialization)
    llm_cache: Any = Field(default=None, exclude=True)
    thread_pool: Any = Field(default=None, exclude=True)
    memory_lock: Any = Field(default=None, exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def sync_legacy_fields(self) -> None:
        """Sync legacy fields from sub-contexts for backward compatibility."""
        self.pages = self.translation.pages
        self.current_page = self.translation.current_page
        self.translations = self.translation.translations
        self.qa_report = self.qa.report
        self.cultural_context = _dict_from_cultural(self.cultural)
        self.memory_context = _dict_from_memory(self.memory)
        self.metadata = self.metadata

    def init_subcontexts(self) -> None:
        """Initialize sub-contexts from legacy fields (for loading existing state)."""
        if not self.translation.pages and self.pages:
            self.translation.pages = self.pages
        if not self.translation.translations and self.translations:
            self.translation.translations = self.translations
        if not self.qa.report and self.qa_report:
            self.qa.report = self.qa_report
        if not self.memory.character_profiles and self.memory_context:
            _load_into_memory(self.memory, self.memory_context)


def _dict_from_cultural(c: CulturalContext) -> dict:
    """Convert CulturalContext to legacy dict format."""
    return c.annotations


def _dict_from_memory(m: MemoryContext) -> dict:
    """Convert MemoryContext to legacy dict format."""
    return {
        "character_profiles": m.character_profiles,
        "page_profiles": m.page_profiles,
        "scene_contexts": m.scene_contexts,
    }


def _load_into_memory(m: MemoryContext, d: dict) -> None:
    """Load legacy dict format into MemoryContext."""
    m.character_profiles = d.get("character_profiles", {})
    m.page_profiles = d.get("page_profiles", {})
    m.scene_contexts = d.get("scene_contexts", {})
