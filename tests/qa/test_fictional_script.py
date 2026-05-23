"""Tests for mga.qa.fictional_script — FictionalScriptProofreader."""

from mga.models import Bubble, Page, TranslationCandidate
from mga.qa.base import QAFeedbackType
from mga.qa.fictional_script import FictionalScriptProofreader


def _make_page(bubbles):
    """Create a Page with the given Bubble dicts."""
    return Page(
        page_id="test_page",
        bubbles=[Bubble(**b) for b in bubbles],
    )


def _make_translations(candidates):
    """Create TranslationCandidate list from dicts."""
    return [TranslationCandidate(**c) for c in candidates]


def test_symbols_lost():
    """Source has symbols, translation doesn't -> WARNING."""
    reader = FictionalScriptProofreader()
    page = _make_page([
        {"bubble_id": "b1", "source_text": "魔法の ✦ 魔法の ✦"},
    ])
    translations = _make_translations([
        {"bubble_id": "b1", "text": "Magic magic magic magic"},
    ])
    feedbacks = reader.proofread(page, translations)
    warnings = [f for f in feedbacks if f.feedback_type == QAFeedbackType.WARNING]
    assert len(warnings) >= 1
    assert any("symbols_lost" in f.category for f in warnings)


def test_symbols_added():
    """Translation has new symbols not in source -> SUGGESTION."""
    reader = FictionalScriptProofreader()
    page = _make_page([
        {"bubble_id": "b1", "source_text": "普通のテキスト"},
    ])
    translations = _make_translations([
        {"bubble_id": "b1", "text": "Normal text ★"},
    ])
    feedbacks = reader.proofread(page, translations)
    suggestions = [f for f in feedbacks if f.feedback_type == QAFeedbackType.SUGGESTION]
    assert len(suggestions) >= 1
    assert any("symbols_added" in f.category for f in suggestions)


def test_mixed_script_term():
    """CJK-katakana mixed term dropped from translation -> SUGGESTION.

    The regex [一-鿿][゠-ヿ]|[゠-ヿ][一-鿿] matches kanji directly
    adjacent to katakana (e.g. 子ス in 硝子スーパー).
    """
    reader = FictionalScriptProofreader()
    # 硝子(kanji) + スーパー(katakana) → mixed script match on "子ス"
    page = _make_page([
        {"bubble_id": "b1", "source_text": "硝子スーパーの術を使った"},
    ])
    translations = _make_translations([
        {"bubble_id": "b1", "text": "Used the glass super technique"},
    ])
    feedbacks = reader.proofread(page, translations)
    suggestions = [f for f in feedbacks if f.feedback_type == QAFeedbackType.SUGGESTION]
    mixed_script = [f for f in suggestions if "mixed_script_term" in f.category]
    assert len(mixed_script) >= 1
    # The regex extracts the 2-char kanji-katakana boundary, not the full term
    assert "子ス" in mixed_script[0].message


def test_clean_no_symbols():
    """No symbols in source or translation should produce no feedback."""
    reader = FictionalScriptProofreader()
    page = _make_page([
        {"bubble_id": "b1", "source_text": "太郎は学校へ行った"},
    ])
    translations = _make_translations([
        {"bubble_id": "b1", "text": "Taro went to school."},
    ])
    feedbacks = reader.proofread(page, translations)
    assert feedbacks == []
