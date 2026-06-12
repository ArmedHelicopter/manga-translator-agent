"""Core domain models — zero-dependency Pydantic schemas."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


# === Enums ===

class TranslationMode(str, Enum):
    MANGA = "manga"
    NOVEL = "novel"


class ProviderRole(str, Enum):
    PRIMARY = "primary"
    FALLBACK = "fallback"
    LOCAL = "local"


# === Pipeline Context ===

class PipelineContext(BaseModel):
    """The universal context object passed through all pipeline stages."""

    project_config: Any = None
    pages: list[Any] = Field(default_factory=list)
    current_page: Any = None
    translations: list[Any] = Field(default_factory=list)
    qa_report: dict = Field(default_factory=dict)
    cultural_context: dict = Field(default_factory=dict)
    memory_context: dict = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    errors: list[dict] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    ocr_guard_state: dict[str, Any] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


# === Translation Entities ===

class TranslationCandidate(BaseModel):
    """A single bubble's translation result."""

    bubble_id: str = ""
    page_id: str = ""
    source_text: str = ""
    translated_text: str = ""
    speaker_id: str | None = None
    footnotes: list[dict] = Field(default_factory=list)
    rationale: str = ""
    provider: str = ""
    model: str = ""
    tokens_used: int = 0

    model_config = {"arbitrary_types_allowed": True}


class CharacterProfile(BaseModel):
    """Compact character memory for prompt injection."""

    character_id: str = ""
    name_jp: str = ""
    name_zh: str = ""
    archetype: str = ""
    speech_patterns: dict[str, str] = Field(default_factory=dict)
    catchphrases: list[str] = Field(default_factory=list)
    tone_spectrum: dict[str, str] = Field(default_factory=dict)
    translation_notes: dict[str, str] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


class SceneContext(BaseModel):
    """Scene-level context for translation."""

    page_id: str = ""
    scene_summary: str = ""
    location: str = ""
    participants: list[str] = Field(default_factory=list)
    mood: str = ""

    model_config = {"arbitrary_types_allowed": True}


# === Provider Config ===

class ProviderRoute(BaseModel):
    provider: str = ""
    model: str = ""


class StageProviderConfig(BaseModel):
    primary: ProviderRoute = Field(default_factory=ProviderRoute)
    fallback: ProviderRoute | None = None
    local: ProviderRoute | None = None


class ProjectConfig(BaseModel):
    """Project configuration — the single source of truth."""

    project_name: str = "manga-project"
    source_lang: str = "ja"
    target_lang: str = "zh-CN"
    working_dir: str = ""
    output_dir: str = ""
    artifact_dir: str = ""
    input_format: str = "images"
    output_format: str = "images"
    pipeline_mode: str = "manga"
    provider_routes: dict[str, StageProviderConfig] = Field(default_factory=dict)
    provider_settings: dict[str, dict] = Field(default_factory=dict)
    plugins: dict[str, dict] = Field(default_factory=dict)

    model_config = {"arbitrary_types_allowed": True}


# === Run Summary ===

class RunSummary(BaseModel):
    """Unified run summary — replaces dual write in OutputStage + CLI."""

    timestamp: str = ""
    pipeline_mode: str = "manga"
    source_lang: str = ""
    target_lang: str = ""
    provider: str = ""
    input_path: str = ""
    output_path: str = ""
    input_format: str = ""
    output_format: str = ""
    page_count: int = 0
    translation_count: int = 0
    stages_completed: list[str] = Field(default_factory=list)
    stage_timings: dict[str, float] = Field(default_factory=dict)
    total_duration: float = 0.0
    error_count: int = 0
    errors: list[dict] = Field(default_factory=list)
    status: str = "completed"
    graph_mode: str = ""
    provider_routes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    runtime: dict[str, Any] = Field(default_factory=dict)
    provider_cascade_errors: list[dict] = Field(default_factory=list)
    provider_cascade_calls: list[dict] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


# === Memory State Entities ===

class CharacterState(BaseModel):
    """Persistent character state in JSON canonical form."""

    character_id: str = ""
    name_jp: str = ""
    name_zh: str = ""
    archetype: str = ""
    speech_patterns: dict[str, str] = Field(default_factory=dict)
    catchphrases: list[str] = Field(default_factory=list)
    tone_spectrum: dict[str, str] = Field(default_factory=dict)
    translation_notes: dict[str, str] = Field(default_factory=dict)
    first_seen: str = ""
    last_updated: str = ""

    @classmethod
    def now(cls) -> str:
        return datetime.now(timezone.utc).isoformat()

    model_config = {"arbitrary_types_allowed": True}


class TermState(BaseModel):
    """Persistent terminology state."""

    term_id: str = ""
    term_jp: str = ""
    term_zh: str = ""
    context: str = ""
    cultural_weight: str = ""
    strategy: str = ""
    frequency: int = 0
    candidate_translations: list[str] = Field(default_factory=list)
    accepted_reason: str = ""
    rejected_reasons: dict[str, str] = Field(default_factory=dict)
    applicability_scope: str = ""

    model_config = {"arbitrary_types_allowed": True}


class SceneState(BaseModel):
    """Persistent scene state."""

    page_id: str = ""
    scene_summary: str = ""
    location: str = ""
    participants: list[str] = Field(default_factory=list)
    mood: str = ""
    first_seen: str = ""
    last_updated: str = ""

    model_config = {"arbitrary_types_allowed": True}


# === Prompt Templates (Token-Optimized) ===

TRANSLATION_SYSTEM_PROMPT = """You are a manga translator. Translate Japanese text to {target_lang} while preserving:
- Character voice and personality
- Cultural nuances with footnotes
- Natural dialogue flow

Output JSON: {{"text": "...", "footnotes": [], "rationale": ""}}"""

SEMANTIC_SYSTEM_PROMPT = """Extract the semantic meaning of Japanese text. Preserve nuance and context."""

PERSONA_SYSTEM_PROMPT = """Render dialogue in the character's voice based on their profile."""

SIMPLE_JSON_SCHEMA = '{"text": "string", "footnotes": "array", "rationale": "string"}'