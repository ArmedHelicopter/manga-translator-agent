"""Tests for mga.qa.base — QAFeedback and QAProofreader base classes."""

from mga.models import Bubble, Page, TranslationCandidate
from mga.qa.base import QAFeedback, QAFeedbackType, QAProofreader


def test_qa_feedback_construction():
    fb = QAFeedback(
        bubble_id="b1",
        feedback_type=QAFeedbackType.ERROR,
        category="fact.number_missing",
        message="Number missing",
    )
    assert fb.bubble_id == "b1"
    assert fb.feedback_type == QAFeedbackType.ERROR
    assert fb.confidence == 1.0
    assert fb.needs_human_review is False


def test_needs_human_review_low_confidence():
    fb = QAFeedback(
        bubble_id="b1",
        feedback_type=QAFeedbackType.WARNING,
        category="test",
        message="test",
        confidence=0.5,
    )
    assert fb.needs_human_review is True


def test_needs_human_review_high_confidence():
    fb = QAFeedback(
        bubble_id="b1",
        feedback_type=QAFeedbackType.WARNING,
        category="test",
        message="test",
        confidence=0.8,
    )
    assert fb.needs_human_review is False


def test_qa_feedback_types():
    assert QAFeedbackType.ERROR.value == "error"
    assert QAFeedbackType.WARNING.value == "warning"
    assert QAFeedbackType.SUGGESTION.value == "suggestion"
