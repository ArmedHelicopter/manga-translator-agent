"""Tests for OCR blank-page detection."""

from __future__ import annotations

import pytest

from mga.models import Bubble, Page
from mga.ocr.detector import BlankPageDetector
from mga.ocr.models import OCRGuardConfig


@pytest.fixture
def make_page():
    """Factory for pages with configurable OCR bubble text."""

    def _factory(page_id: str, page_index: int, bubble_texts: list[str]):
        return Page(
            page_id=page_id,
            page_index=page_index,
            bubbles=[
                Bubble(
                    bubble_id=f"{page_id}-b{i}",
                    source_text=text,
                    reading_order=i,
                )
                for i, text in enumerate(bubble_texts)
            ],
        )

    return _factory


def test_detector_page_blank_no_bubbles(make_page):
    detector = BlankPageDetector(OCRGuardConfig())

    assert detector.is_page_blank(make_page("p001", 1, [])) is True


def test_detector_page_blank_short_text(make_page):
    detector = BlankPageDetector(OCRGuardConfig(min_text_length=3))

    assert detector.is_page_blank(make_page("p001", 1, ["", "  ", "a "])) is True


def test_detector_page_not_blank_sufficient_text(make_page):
    detector = BlankPageDetector(OCRGuardConfig(min_text_length=3))

    assert detector.is_page_blank(make_page("p001", 1, ["", "abc"])) is False


def test_detector_check_sequence_none_below_threshold(make_page):
    detector = BlankPageDetector(OCRGuardConfig(consecutive_blank_threshold=3))
    pages = [
        make_page("p001", 1, []),
        make_page("p002", 2, []),
        make_page("p003", 3, ["abc"]),
    ]

    assert detector.check_sequence(pages) is None


def test_detector_check_sequence_detects_at_threshold(make_page):
    detector = BlankPageDetector(OCRGuardConfig(consecutive_blank_threshold=3))
    pages = [make_page(f"p00{i}", i, []) for i in range(1, 4)]

    sequence = detector.check_sequence(pages)

    assert sequence is not None
    assert sequence.start_index == 1
    assert sequence.end_index == 3
    assert sequence.page_ids == ["p001", "p002", "p003"]
    assert sequence.blank_count == 3


def test_detector_check_sequence_mid_document(make_page):
    detector = BlankPageDetector(OCRGuardConfig(consecutive_blank_threshold=3))
    pages = [
        make_page("p001", 1, ["abc"]),
        make_page("p002", 2, []),
        make_page("p003", 3, [" "]),
        make_page("p004", 4, ["a"]),
        make_page("p005", 5, ["read"]),
    ]

    sequence = detector.check_sequence(pages)

    assert sequence is not None
    assert sequence.start_index == 2
    assert sequence.end_index == 4
    assert sequence.page_ids == ["p002", "p003", "p004"]
    assert sequence.blank_count == 3


def test_detector_check_sequence_at_end(make_page):
    detector = BlankPageDetector(OCRGuardConfig(consecutive_blank_threshold=2))
    pages = [
        make_page("p001", 1, ["read"]),
        make_page("p002", 2, []),
        make_page("p003", 3, []),
    ]

    sequence = detector.check_sequence(pages)

    assert sequence is not None
    assert sequence.start_index == 2
    assert sequence.end_index == 3
    assert sequence.page_ids == ["p002", "p003"]
    assert sequence.blank_count == 2


def test_detector_check_sequence_reset_on_non_blank(make_page):
    detector = BlankPageDetector(OCRGuardConfig(consecutive_blank_threshold=3))
    pages = [
        make_page("p001", 1, []),
        make_page("p002", 2, []),
        make_page("p003", 3, ["read"]),
        make_page("p004", 4, []),
        make_page("p005", 5, []),
    ]

    assert detector.check_sequence(pages) is None


def test_detector_custom_min_text_length(make_page):
    detector = BlankPageDetector(OCRGuardConfig(min_text_length=5))

    assert detector.is_page_blank(make_page("p001", 1, ["four"])) is True
    assert detector.is_page_blank(make_page("p002", 2, ["five!"])) is False


def test_detector_custom_threshold(make_page):
    detector = BlankPageDetector(OCRGuardConfig(consecutive_blank_threshold=1))
    page = make_page("p001", 1, [])

    sequence = detector.check_sequence([page])

    assert sequence is not None
    assert sequence.page_ids == ["p001"]
    assert sequence.blank_count == 1


def test_detector_reset_clears_state(make_page):
    detector = BlankPageDetector(OCRGuardConfig())
    detector._current_blank_pages.append(make_page("p001", 1, []))

    detector.reset()

    assert detector._current_blank_pages == []


def test_detector_multiple_sequences_only_first(make_page):
    detector = BlankPageDetector(OCRGuardConfig(consecutive_blank_threshold=2))
    pages = [
        make_page("p001", 1, []),
        make_page("p002", 2, []),
        make_page("p003", 3, ["read"]),
        make_page("p004", 4, []),
        make_page("p005", 5, []),
    ]

    sequence = detector.check_sequence(pages)

    assert sequence is not None
    assert sequence.page_ids == ["p001", "p002"]
    assert sequence.start_index == 1
    assert sequence.end_index == 2
