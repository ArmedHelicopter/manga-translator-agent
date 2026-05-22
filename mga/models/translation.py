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
    original: str = ""
    translation: str = ""
    type: str = ""


class TranslationCandidate(BaseModel):
    bubble_id: str = ""
    text: str = ""
    rationale: str = ""
    confidence: float = 0.0
    footnotes: List[FootnoteEntry] = Field(default_factory=list)
