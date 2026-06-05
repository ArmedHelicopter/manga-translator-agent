from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PagePair:
    """A paired original + translated page for learning."""
    original_path: str
    translated_path: str
    page_id: str
    alignment_status: str = "filename-only"
    alignment_score: float = 0.0


@dataclass
class AlignedPageData:
    """LLM-extracted data from a single original+translated pair."""
    page_id: str
    source_text: str          # Japanese original (from OCR or text file)
    translated_text: str      # Chinese translation
    characters: list[dict]    # Character identification results
    terminology: list[dict]   # Term extraction
    speech_patterns: dict     # Language patterns per character
    style_notes: str          # Translation style description
    bubble_pairs: list[dict] = field(default_factory=list)
    alignment_status: str = "filename-only"
    alignment_score: float = 0.0


@dataclass
class LearningResult:
    """Full output of the 4-stage learning pipeline."""
    characters: list[dict] = field(default_factory=list)
    terms: list[dict] = field(default_factory=list)
    style_guide: dict = field(default_factory=dict)
    character_graph: dict = field(default_factory=dict)
    alignment: list[dict] = field(default_factory=list)
    alignment_summary: dict[str, int] = field(default_factory=dict)
    quality_report: dict = field(default_factory=dict)
    pages_processed: int = 0
