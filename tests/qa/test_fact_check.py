"""Tests for mga.qa.fact_check — FactCheckProofreader."""

from mga.models import Bubble, Page, PageImage, TranslationCandidate
from mga.qa.fact_check import FactCheckProofreader
from mga.qa.base import QAFeedbackType


def _make_page(bubbles):
    return Page(page_id="p1", image=PageImage(path="test.png"), bubbles=bubbles)


def test_number_missing_in_translation():
    reader = FactCheckProofreader()
    page = _make_page([Bubble(bubble_id="b1", source_text="3人の仲間")])
    translations = [TranslationCandidate(bubble_id="b1", text="Three friends")]
    feedbacks = reader.proofread(page, translations, {})
    number_errors = [f for f in feedbacks if f.category == "fact.number_missing"]
    assert len(number_errors) >= 1
    assert number_errors[0].feedback_type == QAFeedbackType.ERROR


def test_number_added_in_translation():
    reader = FactCheckProofreader()
    page = _make_page([Bubble(bubble_id="b1", source_text="仲間")])
    translations = [TranslationCandidate(bubble_id="b1", text="3人の友達")]
    feedbacks = reader.proofread(page, translations, {})
    number_added = [f for f in feedbacks if f.category == "fact.number_added"]
    assert len(number_added) >= 1


def test_no_issues_clean_translation():
    reader = FactCheckProofreader()
    page = _make_page([Bubble(bubble_id="b1", source_text="こんにちは")])
    translations = [TranslationCandidate(bubble_id="b1", text="你好")]
    feedbacks = reader.proofread(page, translations, {})
    assert len(feedbacks) == 0


def test_omission_warning():
    reader = FactCheckProofreader()
    page = _make_page([Bubble(bubble_id="b1", source_text="長いテキストです")])
    translations = [TranslationCandidate(bubble_id="b1", text="短")]
    feedbacks = reader.proofread(page, translations, {})
    omission = [f for f in feedbacks if f.category == "fact.possible_omission"]
    assert len(omission) >= 1


def test_name_missing():
    reader = FactCheckProofreader()
    page = _make_page([Bubble(bubble_id="b1", source_text="田中さんが来る")])
    translations = [TranslationCandidate(bubble_id="b1", text="He is coming")]
    feedbacks = reader.proofread(page, translations, {"character_names": ["田中"]})
    name_issues = [f for f in feedbacks if f.category == "fact.name_missing"]
    assert len(name_issues) >= 1
