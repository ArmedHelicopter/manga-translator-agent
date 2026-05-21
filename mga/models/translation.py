"""Translation data models."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class Utterance(BaseModel):
    bubble_id: str = ""
    source_text: str = ""
    speaker: Optional[str] = None
    tone: Optional[str] = None
    context_notes: Optional[str] = None


class TranslationCandidate(BaseModel):
    bubble_id: str = ""
    text: str = ""
    rationale: str = ""
    confidence: float = 0.0
