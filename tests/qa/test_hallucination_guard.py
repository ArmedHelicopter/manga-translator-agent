"""Tests for mga.qa.hallucination_guard — HallucinationGuardProofreader."""

from mga.models import Bubble, Page, PageImage, TranslationCandidate
from mga.qa.base import QAFeedbackType
from mga.qa.hallucination_guard import HallucinationGuardProofreader


def _make_page(bubbles):
    """Create a Page with the given bubbles."""
    return Page(page_id="p1", image=PageImage(path="test.png"), bubbles=bubbles)


def _make_translations(candidates):
    """Passthrough — list of TranslationCandidate already correct type."""
    return candidates


# ── Clean / no-issue cases ─────────────────────────────────────


def test_clean_translation_no_issues():
    """Normal translation with no hallucination signals produces no feedback."""
    reader = HallucinationGuardProofreader()
    page = _make_page([Bubble(bubble_id="b1", source_text="おはよう")])
    # Use non-CJK translation to avoid false positives from the CJK name regex
    translations = _make_translations([
        TranslationCandidate(bubble_id="b1", text="Hello!"),
    ])

    feedbacks = reader.proofread(page, translations, {})
    assert feedbacks == []


def test_no_context_provided():
    """Empty context dict works without errors."""
    reader = HallucinationGuardProofreader()
    page = _make_page([Bubble(bubble_id="b1", source_text="テスト")])
    translations = _make_translations([
        TranslationCandidate(bubble_id="b1", text="测试"),
    ])

    feedbacks = reader.proofread(page, translations, None)
    assert isinstance(feedbacks, list)


# ── Name fidelity ──────────────────────────────────────────────


def test_name_missing_from_translation():
    """Known character name in source missing from translation emits WARNING."""
    reader = HallucinationGuardProofreader()
    page = _make_page([
        Bubble(bubble_id="b1", source_text="田中さんが来る"),
    ])
    translations = _make_translations([
        TranslationCandidate(bubble_id="b1", text="他来了"),
    ])
    context = {
        "character_profiles": {
            "tanaka": {"name_jp": "田中", "name_zh": "田中"},
        },
    }

    feedbacks = reader.proofread(page, translations, context)

    name_issues = [f for f in feedbacks if "name_missing" in f.category]
    assert len(name_issues) >= 1
    assert name_issues[0].feedback_type == QAFeedbackType.WARNING
    assert "田中" in name_issues[0].message


def test_possible_invented_name():
    """Name in translation not in source or known profiles emits SUGGESTION."""
    reader = HallucinationGuardProofreader()
    page = _make_page([
        Bubble(bubble_id="b1", source_text="今日はいい天気ですね"),
    ])
    translations = _make_translations([
        TranslationCandidate(bubble_id="b1", text="佐藤说今天天气真好"),
    ])
    context = {"character_profiles": {}}

    feedbacks = reader.proofread(page, translations, context)

    invented = [f for f in feedbacks if "invented_name" in f.category]
    assert len(invented) >= 1
    assert invented[0].feedback_type == QAFeedbackType.SUGGESTION


# ── Number fidelity ────────────────────────────────────────────


def test_number_mismatch():
    """Source has '3' but translation has '5' emits WARNING."""
    reader = HallucinationGuardProofreader()
    page = _make_page([
        Bubble(bubble_id="b1", source_text="3人の仲間がいる"),
    ])
    translations = _make_translations([
        TranslationCandidate(bubble_id="b1", text="有5个伙伴"),
    ])

    feedbacks = reader.proofread(page, translations, {})

    number_issues = [f for f in feedbacks if "number" in f.category]
    assert len(number_issues) >= 1
    assert any(f.feedback_type == QAFeedbackType.WARNING for f in number_issues)


def test_numbers_lost():
    """Source has numbers but translation has none emits WARNING."""
    reader = HallucinationGuardProofreader()
    page = _make_page([
        Bubble(bubble_id="b1", source_text="第3章と第7章"),
    ])
    translations = _make_translations([
        TranslationCandidate(bubble_id="b1", text="第三章和第七章"),
    ])

    feedbacks = reader.proofread(page, translations, {})

    lost = [f for f in feedbacks if f.category == "hallucination.numbers_lost"]
    assert len(lost) >= 1
    assert lost[0].feedback_type == QAFeedbackType.WARNING


# ── Term consistency ───────────────────────────────────────────


def test_term_inconsistency():
    """Term in terminology DB not found in translation emits feedback."""
    reader = HallucinationGuardProofreader()
    page = _make_page([
        Bubble(bubble_id="b1", source_text="彼は忍者だ"),
    ])
    translations = _make_translations([
        TranslationCandidate(bubble_id="b1", text="他是武士"),
    ])
    context = {
        "terminology": {"忍者": "忍者"},
    }

    feedbacks = reader.proofread(page, translations, context)

    term_issues = [f for f in feedbacks if "term" in f.category]
    assert len(term_issues) >= 1
    assert "忍者" in term_issues[0].message
