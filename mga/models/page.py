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


class Bubble(BaseModel):
    bubble_id: str = ""
    bbox: BoundingBox = Field(default_factory=BoundingBox)
    source_text: str = ""
    reading_order: int = 0
    speaker_id: Optional[str] = None
    speaker_name: Optional[str] = None
    tone: Optional[str] = None
    notes: Optional[str] = None


class Page(BaseModel):
    page_id: str = ""
    page_index: int = 0
    image: PageImage = Field(default_factory=PageImage)
    source_lang: str = "ja"
    bubbles: List[Bubble] = Field(default_factory=list)
    scene_summary: str = ""
