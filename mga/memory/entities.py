"""Pydantic models for memory entities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class CharacterState(BaseModel):
    """Structured state for a character's translation profile."""

    character_id: str = ""
    name_jp: str = ""
    name_zh: str = ""
    archetype: str = ""
    speech_patterns: dict[str, str] = Field(default_factory=dict)
    catchphrases: list[str] = Field(default_factory=list)
    tone_spectrum: dict[str, str] = Field(default_factory=dict)
    translation_notes: dict[str, str] = Field(default_factory=dict)
    voice_evolutions: list[dict[str, Any]] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class SceneState(BaseModel):
    """Structured state for a scene's translation context."""

    scene_id: str = ""
    chapter: int = 0
    page: int = 0
    scene_description: str = ""
    characters: list[str] = Field(default_factory=list)
    mood: str = ""
    narrative_summary: str = ""


class TermState(BaseModel):
    """Structured state for a terminology entry."""

    term_id: str = ""
    term_jp: str = ""
    term_zh: str = ""
    context: str = ""
    cultural_weight: str = ""
    strategy: str = ""
    frequency: int = 0


class DecisionState(BaseModel):
    """Structured state for a translation decision."""

    decision_id: str = ""
    stage: str = ""
    input_ref: str = ""
    decision: str = ""
    rationale: str = ""
    confidence: float = 0.0
    timestamp: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )


class MemoryIndex(BaseModel):
    """Top-level index linking all memory entities."""

    characters: dict[str, str] = Field(default_factory=dict)
    scenes: dict[str, str] = Field(default_factory=dict)
    terms: dict[str, str] = Field(default_factory=dict)
    decisions: dict[str, str] = Field(default_factory=dict)
    version: int = 1
    last_updated: str = Field(
        default_factory=lambda: datetime.now().isoformat()
    )
