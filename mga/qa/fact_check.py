"""Fact-check proofreader: verifies factual consistency of translations."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from mga.models import Page, TranslationCandidate

from .base import QAFeedback, QAFeedbackType, QAProofreader

FACT_CHECK_PROMPT = (
    "You are a manga translation fact-checker.\n"
    "Source: {source_text}\n"
    "Translation: {translated_text}\n"
    "Return JSON: {{issues: [{{category, message, confidence, suggested_text}}]}}"
)


class FactCheckProofreader(QAProofreader):
    """Checks factual consistency: names, numbers, places match source."""

    @property
    def name(self) -> str:
        return "fact_check"

    @property
    def priority(self) -> int:
        return 10

    def proofread(
        self, page: Page, translations: List[TranslationCandidate],
        context: Dict[str, Any],
    ) -> List[QAFeedback]:
        feedbacks: List[QAFeedback] = []
        for candidate in translations:
            bubble = self._get_bubble(page, candidate.bubble_id)
            if bubble is None:
                continue
            feedbacks.extend(self._check_numbers(bubble, candidate))
            feedbacks.extend(self._check_names(bubble, candidate, context))
            feedbacks.extend(self._check_length_delta(bubble, candidate))
        return feedbacks

    def _check_numbers(
        self, bubble: Any, candidate: TranslationCandidate,
    ) -> List[QAFeedback]:
        source_nums = set(re.findall(r"\d+", bubble.source_text))
        trans_nums = set(re.findall(r"\d+", candidate.text))
        feedbacks = []
        for n in source_nums - trans_nums:
            feedbacks.append(QAFeedback(
                bubble_id=candidate.bubble_id,
                feedback_type=QAFeedbackType.ERROR,
                category="fact.number_missing",
                message=f"Number '{n}' from source not found in translation",
                confidence=0.9,
                original_text=bubble.source_text,
                suggested_text=candidate.text,
                rationale="Numeric values must be preserved exactly",
            ))
        for n in trans_nums - source_nums:
            feedbacks.append(QAFeedback(
                bubble_id=candidate.bubble_id,
                feedback_type=QAFeedbackType.WARNING,
                category="fact.number_added",
                message=f"Number '{n}' appears in translation but not in source",
                confidence=0.8,
                original_text=bubble.source_text,
                suggested_text=candidate.text,
                rationale="Translation should not introduce new numeric values",
            ))
        return feedbacks

    def _check_names(
        self, bubble: Any, candidate: TranslationCandidate, context: Dict[str, Any],
    ) -> List[QAFeedback]:
        known_names = context.get("character_names", [])
        return [QAFeedback(
            bubble_id=candidate.bubble_id,
            feedback_type=QAFeedbackType.WARNING,
            category="fact.name_missing",
            message=f"Character name '{name}' in source not preserved",
            confidence=0.75,
            original_text=bubble.source_text,
            suggested_text=candidate.text,
            rationale="Character names should be preserved or transliterated",
        ) for name in known_names
            if name in bubble.source_text and name not in candidate.text]

    def _check_length_delta(
        self, bubble: Any, candidate: TranslationCandidate,
    ) -> List[QAFeedback]:
        src_len = len(bubble.source_text)
        if src_len == 0:
            return []
        ratio = len(candidate.text) / src_len
        if ratio < 0.3:
            return [QAFeedback(
                bubble_id=candidate.bubble_id,
                feedback_type=QAFeedbackType.WARNING,
                category="fact.possible_omission",
                message="Translation is much shorter than source -- possible omission",
                confidence=0.6,
                original_text=bubble.source_text,
                suggested_text=candidate.text,
                rationale="Extreme length reduction may indicate dropped information",
            )]
        if ratio > 3.0:
            return [QAFeedback(
                bubble_id=candidate.bubble_id,
                feedback_type=QAFeedbackType.WARNING,
                category="fact.possible_addition",
                message="Translation is much longer than source -- possible addition",
                confidence=0.6,
                original_text=bubble.source_text,
                suggested_text=candidate.text,
                rationale="Extreme length increase may indicate hallucinated content",
            )]
        return []
