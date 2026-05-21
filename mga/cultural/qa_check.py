"""Cultural QA — terminology and strategy consistency checks."""

from __future__ import annotations

import logging
import re
from typing import Any

from mga.models import Bubble, Page, TranslationCandidate
from mga.qa.base import QAFeedback, QAFeedbackType, QAProofreader

logger = logging.getLogger(__name__)


class CulturalQAProofreader(QAProofreader):
    """Check terminology consistency and strategy adherence."""

    @property
    def name(self) -> str:
        return "cultural_qa"

    @property
    def priority(self) -> int:
        return 35

    def proofread(
        self,
        page: Page,
        translations: list[TranslationCandidate],
        context: dict[str, Any] | None = None,
    ) -> list[QAFeedback]:
        context = context or {}
        feedbacks: list[QAFeedback] = []

        # Load terminology DB
        terminology = context.get("terminology", {})
        project_dir = context.get("project_dir", "")

        for candidate in translations:
            bubble = self._get_bubble(page, candidate.bubble_id)
            if not bubble:
                continue

            # Check 1: Terminology consistency
            feedbacks.extend(self._check_terminology(bubble, candidate, terminology))

            # Check 2: Coined term preservation
            feedbacks.extend(self._check_coined_terms(bubble, candidate))

            # Check 3: Honorific presence
            feedbacks.extend(self._check_honorifics(bubble, candidate))

        return feedbacks

    def _check_terminology(
        self,
        bubble: Bubble,
        candidate: TranslationCandidate,
        terminology: dict,
    ) -> list[QAFeedback]:
        """Check that confirmed terms are used consistently."""
        feedbacks = []
        if not terminology:
            return feedbacks

        for jp_term, term_data in terminology.items():
            if not isinstance(term_data, dict):
                continue
            if not term_data.get("confirmed", False):
                continue

            zh_term = term_data.get("term_target", "") or term_data.get("term_zh", "")
            if jp_term in bubble.source_text and zh_term and zh_term not in candidate.text:
                feedbacks.append(QAFeedback(
                    bubble_id=candidate.bubble_id,
                    feedback_type=QAFeedbackType.WARNING,
                    category="cultural.term_inconsistent",
                    message=f"Confirmed term '{jp_term}' (->'{zh_term}') not used in translation",
                    confidence=0.7,
                ))

        return feedbacks

    def _check_coined_terms(
        self,
        bubble: Bubble,
        candidate: TranslationCandidate,
    ) -> list[QAFeedback]:
        """Check that coined terms are preserved (not translated)."""
        feedbacks = []
        # Katakana terms in source that might be coined
        katakana = re.findall(r"[゠-ヿ]{3,}", bubble.source_text)
        for term in katakana:
            # If the term appears in source but a different form appears in translation
            if term in bubble.source_text and term not in candidate.text:
                # Check if it was intentionally translated or just dropped
                feedbacks.append(QAFeedback(
                    bubble_id=candidate.bubble_id,
                    feedback_type=QAFeedbackType.SUGGESTION,
                    category="cultural.coined_term_translated",
                    message=f"Katakana term '{term}' not preserved in translation",
                    confidence=0.4,
                ))

        return feedbacks

    def _check_honorifics(
        self,
        bubble: Bubble,
        candidate: TranslationCandidate,
    ) -> list[QAFeedback]:
        """Check that honorific markers are handled."""
        feedbacks = []
        honorifics = ["さん", "くん", "ちゃん", "様", "殿", "先生"]
        for h in honorifics:
            if h in bubble.source_text and h not in candidate.text:
                # Honorific was removed — this might be OK but worth flagging
                feedbacks.append(QAFeedback(
                    bubble_id=candidate.bubble_id,
                    feedback_type=QAFeedbackType.SUGGESTION,
                    category="cultural.honorific_removed",
                    message=f"Honorific '{h}' from source not present in translation",
                    confidence=0.3,
                ))

        return feedbacks
