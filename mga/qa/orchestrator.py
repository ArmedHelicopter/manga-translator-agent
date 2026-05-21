"""QA Orchestrator: runs all proofreaders and produces a structured report."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List, Optional

from mga.models import Page, TranslationCandidate

from .base import QAFeedback, QAFeedbackType, QAProofreader
from .character_consistency import CharacterConsistencyProofreader
from .dialog_hierarchy import DialogHierarchyProofreader
from .emotion_consistency import EmotionConsistencyProofreader
from .fact_check import FactCheckProofreader
from .language_evolution import LanguageEvolutionProofreader
from .style_polish import StylePolishProofreader

_DEFAULT_PROOFREADERS: list[QAProofreader] = [
    FactCheckProofreader(),
    CharacterConsistencyProofreader(),
    DialogHierarchyProofreader(),
    EmotionConsistencyProofreader(),
    LanguageEvolutionProofreader(),
    StylePolishProofreader(),
]


class QAOrchestrator:
    """Runs all registered proofreaders in priority order and formats results."""

    def __init__(
        self,
        proofreaders: Optional[List[QAProofreader]] = None,
    ) -> None:
        readers = proofreaders if proofreaders is not None else _DEFAULT_PROOFREADERS
        self._proofreaders = sorted(readers, key=lambda r: r.priority)

    @property
    def proofreaders(self) -> List[QAProofreader]:
        return list(self._proofreaders)

    def proofread(
        self,
        page: Page,
        translations: List[TranslationCandidate],
        context: Optional[Dict[str, Any]] = None,
    ) -> List[QAFeedback]:
        """Run all proofreaders in priority order and return merged feedback."""
        ctx = context or {}
        all_feedbacks: List[QAFeedback] = []
        for reader in self._proofreaders:
            try:
                findings = reader.proofread(page, translations, ctx)
                all_feedbacks.extend(findings)
            except Exception as exc:
                all_feedbacks.append(QAFeedback(
                    bubble_id="",
                    feedback_type=QAFeedbackType.ERROR,
                    category=f"orchestrator.{reader.name}_failed",
                    message=f"Proofreader '{reader.name}' raised: {exc}",
                    confidence=1.0,
                    rationale="Internal proofreader failure",
                ))
        return all_feedbacks

    @staticmethod
    def group_by_bubble(
        feedbacks: List[QAFeedback],
    ) -> Dict[str, List[QAFeedback]]:
        """Group feedback items by bubble_id for per-bubble review."""
        groups: Dict[str, List[QAFeedback]] = defaultdict(list)
        for fb in feedbacks:
            groups[fb.bubble_id].append(fb)
        return dict(groups)

    @staticmethod
    def format_report(feedbacks: List[QAFeedback]) -> Dict[str, Any]:
        """Produce a structured QA report from a list of feedbacks."""
        by_type: Dict[str, int] = defaultdict(int)
        by_category: Dict[str, int] = defaultdict(int)
        needs_review = 0
        for fb in feedbacks:
            by_type[fb.feedback_type.value] += 1
            by_category[fb.category] += 1
            if fb.needs_human_review:
                needs_review += 1

        return {
            "total_findings": len(feedbacks),
            "by_type": dict(by_type),
            "by_category": dict(by_category),
            "needs_human_review": needs_review,
            "findings": [fb.model_dump() for fb in feedbacks],
            "passed": len(feedbacks) == 0,
        }
