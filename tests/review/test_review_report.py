from mga.models import TranslationCandidate
from mga.review.report import generate_review_report


def test_review_report_treats_qa_feedback_type_error_as_human_review():
    report = generate_review_report(
        translations=[TranslationCandidate(bubble_id="b1", text="bad translation")],
        qa_report={
            "findings": [
                {
                    "bubble_id": "b1",
                    "feedback_type": "error",
                    "category": "fact.number_missing",
                    "message": "Number missing",
                    "confidence": 0.9,
                }
            ]
        },
        context={"page_id": "p1", "source_texts": ["source text"]},
    )

    assert report.score == 0.7
    assert report.needs_human_review is True


def test_review_report_preserves_legacy_severity_scoring():
    report = generate_review_report(
        translations=[TranslationCandidate(bubble_id="b1", text="translation")],
        qa_report={
            "findings": [
                {
                    "bubble_id": "b1",
                    "severity": "critical",
                    "message": "Wrong translation",
                }
            ]
        },
        context={"page_id": "p1", "source_texts": ["source text"]},
    )

    assert report.score == 0.7
    assert report.needs_human_review is True


def test_review_report_marks_low_confidence_qa_finding_for_human_review():
    report = generate_review_report(
        translations=[TranslationCandidate(bubble_id="b1", text="translation")],
        qa_report={
            "findings": [
                {
                    "bubble_id": "b1",
                    "feedback_type": "warning",
                    "message": "Reviewer confidence is low",
                    "confidence": 0.5,
                }
            ]
        },
        context={"page_id": "p1", "source_texts": ["source text"]},
    )

    assert report.score == 0.85
    assert report.needs_human_review is True
