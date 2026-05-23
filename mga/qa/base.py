"""Base classes for the QA proofreading layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from mga.models import Page, TranslationCandidate


class QAFeedbackType(str, Enum):
    """Severity classification for QA feedback items."""

    ERROR = "error"
    WARNING = "warning"
    SUGGESTION = "suggestion"


class QAFeedback(BaseModel):
    """A single QA finding attached to a translated bubble."""

    bubble_id: str
    feedback_type: QAFeedbackType
    category: str
    message: str
    confidence: float = 1.0
    original_text: str = ""
    suggested_text: str = ""
    rationale: str = ""

    @property
    def needs_human_review(self) -> bool:
        """Low-confidence findings require human review per SPEC 6.3."""
        return self.confidence < 0.7


class QAProofreader(ABC):
    """Abstract base for all QA proofreaders."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this proofreader."""

    @property
    @abstractmethod
    def priority(self) -> int:
        """Execution order — lower runs first (SPEC 6.3 priority list)."""

    @abstractmethod
    def proofread(
        self,
        page: Page,
        translations: List[TranslationCandidate],
        context: Dict[str, Any],
    ) -> List[QAFeedback]:
        """Run checks and return findings for this proofreader's domain."""

    def _get_bubble(
        self, page: Page, bubble_id: str
    ) -> Optional[Any]:
        """Look up a bubble by id on the page."""
        for b in page.bubbles:
            if b.bubble_id == bubble_id:
                return b
        return None

    def _get_candidate(
        self, translations: List[TranslationCandidate], bubble_id: str
    ) -> Optional[TranslationCandidate]:
        """Look up a translation candidate by bubble id."""
        for c in translations:
            if c.bubble_id == bubble_id:
                return c
        return None
