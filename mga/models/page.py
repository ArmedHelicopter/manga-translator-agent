"""Page and bubble data models."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0


class PageImage(BaseModel):
    path: str = ""
    width: int = 0
    height: int = 0
    dpi: Optional[int] = None


class VisualFootnote(BaseModel):
    source_text: str = ""
    translation_hint: str = ""
    kind: str = "other"
    bbox: Optional[BoundingBox] = None
    notes: Optional[str] = None
    explanation: Optional[str] = None  # Detailed cultural/explanatory note


class PageFootnote(BaseModel):
    """A compiled footnote for the page-level footnote section."""
    index: int = 0  # Footnote number (1, 2, 3...)
    term: str = ""  # Original Japanese term
    translation: str = ""  # Translation used in text
    explanation: str = ""  # Full explanation
    type: str = "loanword"  # "loanword" | "coined" | "cultural" | "fictional" | "sfx"
    source_bubble_id: Optional[str] = None  # Which bubble this footnote came from


class Bubble(BaseModel):
    bubble_id: str = ""
    bbox: BoundingBox = Field(default_factory=BoundingBox)
    source_text: str = ""
    reading_order: int = 0
    speaker_id: Optional[str] = None
    speaker_name: Optional[str] = None
    tone: Optional[str] = None
    notes: Optional[str] = None
    box_type: str = "dialogue"
    provisional_speaker: Optional[str] = None
    voice_hint: Optional[str] = None
    vision_notes: Optional[str] = None
    detection_source: Optional[str] = None  # "ocr" | "vision" | "fallback"
    vision_confidence: Optional[float] = None  # confidence score from vision detection


class Page(BaseModel):
    page_id: str = ""
    page_index: int = 0
    image: PageImage = Field(default_factory=PageImage)
    source_lang: str = "ja"
    source_text: str = ""
    bubbles: List[Bubble] = Field(default_factory=list)
    scene_summary: str = ""
    visual_footnotes: List[VisualFootnote] = Field(default_factory=list)
    voice_hints: List[str] = Field(default_factory=list)
    page_footnotes: List[PageFootnote] = Field(default_factory=list)  # Compiled page-level footnotes
