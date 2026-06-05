"""Tests for mga.cultural.qa_check — CulturalQAProofreader."""

from mga.cultural.qa_check import CulturalQAProofreader
from mga.models import Bubble, Page, TranslationCandidate
from mga.qa.base import QAFeedbackType


def _make_page(bubbles):
    """Create a Page with the given Bubble dicts."""
    return Page(
        page_id="test_page",
        bubbles=[Bubble(**b) for b in bubbles],
    )


def _make_translations(candidates):
    """Create TranslationCandidate list from dicts."""
    return [TranslationCandidate(**c) for c in candidates]


def test_clean_translation():
    """No issues should produce no feedback."""
    reader = CulturalQAProofreader()
    page = _make_page([
        {"bubble_id": "b1", "source_text": "太郎は行く"},
    ])
    translations = _make_translations([
        {"bubble_id": "b1", "text": "太郎 goes."},
    ])
    feedbacks = reader.proofread(page, translations, context={})
    assert feedbacks == []


def test_term_inconsistency(tmp_path):
    """Confirmed term in source but not in translation should produce WARNING."""
    reader = CulturalQAProofreader()
    page = _make_page([
        {"bubble_id": "b1", "source_text": "田中さんによると、刀を研ぐ必要がある"},
    ])
    translations = _make_translations([
        {"bubble_id": "b1", "text": "According to Tanaka, the blade needs sharpening"},
    ])
    # Supply terminology with a confirmed term for 刀 -> sword
    terminology = {
        "刀": {
            "confirmed": True,
            "term_target": "sword",
            "strategy": "preserve",
        },
    }
    feedbacks = reader.proofread(page, translations, context={"terminology": terminology})
    warnings = [f for f in feedbacks if f.feedback_type == QAFeedbackType.WARNING]
    assert len(warnings) >= 1
    assert any("刀" in f.message for f in warnings)


def test_coined_term_translated():
    """Katakana term present in source but missing from translation -> SUGGESTION."""
    reader = CulturalQAProofreader()
    page = _make_page([
        {"bubble_id": "b1", "source_text": "ファイアボールを放て"},
    ])
    translations = _make_translations([
        {"bubble_id": "b1", "text": "Shoot the flame orb"},
    ])
    feedbacks = reader.proofread(page, translations, context={})
    suggestions = [f for f in feedbacks if f.feedback_type == QAFeedbackType.SUGGESTION]
    assert len(suggestions) >= 1
    assert any("ファイアボール" in f.message for f in suggestions)


def test_honorific_removed():
    """Honorific in source but not in translation should produce SUGGESTION."""
    reader = CulturalQAProofreader()
    page = _make_page([
        {"bubble_id": "b1", "source_text": "田中さん、お元気ですか"},
    ])
    translations = _make_translations([
        {"bubble_id": "b1", "text": "Tanaka, how are you"},
    ])
    feedbacks = reader.proofread(page, translations, context={})
    suggestions = [f for f in feedbacks if f.feedback_type == QAFeedbackType.SUGGESTION]
    honorific_feedback = [f for f in suggestions if "さん" in f.message]
    assert len(honorific_feedback) >= 1


def test_no_context():
    """Empty context should not cause errors."""
    reader = CulturalQAProofreader()
    page = _make_page([
        {"bubble_id": "b1", "source_text": "太郎は行く"},
    ])
    translations = _make_translations([
        {"bubble_id": "b1", "text": "Taro goes."},
    ])
    feedbacks = reader.proofread(page, translations, context=None)
    assert isinstance(feedbacks, list)


def test_strategy_consistency_flags_missing_preserved_term():
    """Preserve-style strategy analysis should be visible in the translation."""
    reader = CulturalQAProofreader()
    page = _make_page([
        {"bubble_id": "b1", "source_text": "GLASSJOIN activates"},
    ])
    translations = _make_translations([
        {"bubble_id": "b1", "text": "The repair art activates"},
    ])

    feedbacks = reader.proofread(
        page,
        translations,
        context={
            "cultural_analysis": {
                "b1": [
                    {
                        "term": "GLASSJOIN",
                        "strategy": "preserve",
                    }
                ]
            }
        },
    )

    assert any(f.category == "cultural.strategy_inconsistent" for f in feedbacks)


def test_strategy_consistency_accepts_term_footnote():
    """Footnotes count as visible handling for preserve-style strategy terms."""
    reader = CulturalQAProofreader()
    page = _make_page([
        {"bubble_id": "b1", "source_text": "GLASSJOIN activates"},
    ])
    translations = _make_translations([
        {
            "bubble_id": "b1",
            "text": "The repair art activates",
            "footnotes": [
                {
                    "original": "GLASSJOIN",
                    "translation": "glass joining",
                    "type": "loanword",
                }
            ],
        },
    ])

    feedbacks = reader.proofread(
        page,
        translations,
        context={
            "cultural_analysis": {
                "b1": [
                    {
                        "term": "GLASSJOIN",
                        "strategy": "preserve",
                    }
                ]
            }
        },
    )

    assert not any(f.category == "cultural.strategy_inconsistent" for f in feedbacks)
