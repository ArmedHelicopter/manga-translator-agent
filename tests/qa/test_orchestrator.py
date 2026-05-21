"""Tests for mga.qa.orchestrator — QAOrchestrator."""

from mga.models import Bubble, Page, PageImage, TranslationCandidate
from mga.qa.orchestrator import QAOrchestrator
from mga.qa.base import QAFeedback, QAFeedbackType


def _make_page(bubbles):
    return Page(page_id="p1", image=PageImage(path="test.png"), bubbles=bubbles)


def test_orchestrator_runs_all_proofreaders():
    orch = QAOrchestrator()
    assert len(orch.proofreaders) == 8


def test_orchestrator_proofread_clean():
    orch = QAOrchestrator()
    page = _make_page([Bubble(bubble_id="b1", source_text="こんにちは")])
    translations = [TranslationCandidate(bubble_id="b1", text="你好")]
    feedbacks = orch.proofread(page, translations, {})
    # Clean translation may still get style suggestions, but no errors
    errors = [f for f in feedbacks if f.feedback_type == QAFeedbackType.ERROR]
    assert len(errors) == 0


def test_orchestrator_proofread_with_errors():
    orch = QAOrchestrator()
    page = _make_page([Bubble(bubble_id="b1", source_text="3人の仲間")])
    translations = [TranslationCandidate(bubble_id="b1", text="Friends")]
    feedbacks = orch.proofread(page, translations, {})
    errors = [f for f in feedbacks if f.feedback_type == QAFeedbackType.ERROR]
    assert len(errors) >= 1


def test_group_by_bubble():
    feedbacks = [
        QAFeedback(bubble_id="b1", feedback_type=QAFeedbackType.ERROR, category="c1", message="m1"),
        QAFeedback(bubble_id="b1", feedback_type=QAFeedbackType.WARNING, category="c2", message="m2"),
        QAFeedback(bubble_id="b2", feedback_type=QAFeedbackType.ERROR, category="c1", message="m3"),
    ]
    groups = QAOrchestrator.group_by_bubble(feedbacks)
    assert len(groups["b1"]) == 2
    assert len(groups["b2"]) == 1


def test_format_report():
    feedbacks = [
        QAFeedback(bubble_id="b1", feedback_type=QAFeedbackType.ERROR, category="c1", message="m1"),
        QAFeedback(bubble_id="b2", feedback_type=QAFeedbackType.WARNING, category="c1", message="m2", confidence=0.5),
    ]
    report = QAOrchestrator.format_report(feedbacks)
    assert report["total_findings"] == 2
    assert report["by_type"]["error"] == 1
    assert report["by_type"]["warning"] == 1
    assert report["needs_human_review"] == 1
    assert report["passed"] is False


def test_format_report_clean():
    report = QAOrchestrator.format_report([])
    assert report["passed"] is True
    assert report["total_findings"] == 0
