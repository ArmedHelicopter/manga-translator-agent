"""Translation data models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class Utterance(BaseModel):
    bubble_id: str = ""
    source_text: str = ""
    speaker: Optional[str] = None
    tone: Optional[str] = None
    context_notes: Optional[str] = None


class FootnoteEntry(BaseModel):
    """A single footnote entry for loanwords, coined terms, or cultural references."""
    original: str = ""
    translation: str = ""
    type: str = ""  # "loanword" | "coined" | "cultural" | "sfx" | "fictional"
    explanation: Optional[str] = None  # Detailed explanation (e.g., cultural background)


class TranslationCandidate(BaseModel):
    bubble_id: str = ""
    text: str = ""
    rationale: str = ""
    confidence: float = 0.0
    footnotes: List[FootnoteEntry] = Field(default_factory=list)


class SemanticTranslation(BaseModel):
    bubble_id: str = ""
    text: str = ""
    speech_act: Optional[str] = None
    emotion: Optional[str] = None
    must_preserve: List[str] = Field(default_factory=list)
    footnotes: List[FootnoteEntry] = Field(default_factory=list)
    rationale: str = ""
    confidence: float = 0.0


class PersonaRenderTrace(BaseModel):
    bubble_id: str = ""
    speaker_id: Optional[str] = None
    listener_id: Optional[str] = None
    semantic_text: str = ""
    rendered_text: str = ""
    persona_moves: List[str] = Field(default_factory=list)
    relationship_context_used: bool = False
    memory_context_used: bool = False
    vision_context_used: bool = False
    rationale: str = ""
    confidence: float = 0.0


class TranslationProviderTrace(BaseModel):
    semantic: dict = Field(default_factory=dict)
    persona: dict = Field(default_factory=dict)


class DialogueRealizationTrace(BaseModel):
    page_id: str = ""
    bubble_id: str = ""
    source_text: str = ""
    speaker_id: Optional[str] = None
    provisional_speaker: Optional[str] = None
    semantic: SemanticTranslation = Field(default_factory=SemanticTranslation)
    persona: PersonaRenderTrace = Field(default_factory=PersonaRenderTrace)
    provider: TranslationProviderTrace = Field(default_factory=TranslationProviderTrace)
    final_text: str = ""
