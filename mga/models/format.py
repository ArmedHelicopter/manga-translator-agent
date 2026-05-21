"""Format-related data models."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class PageRef(BaseModel):
    index: int = 0
    image_path: str = ""
    original_ref: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TranslatedPage(BaseModel):
    index: int = 0
    image_path: str = ""
    page_json: Optional[Dict[str, Any]] = None
    qa_report: Optional[Dict[str, Any]] = None
