"""Blank-page detection for OCR artifact output."""

from __future__ import annotations

import logging

from mga.models import Page

from .models import BlankPageSequence, OCRGuardConfig

logger = logging.getLogger(__name__)


class BlankPageDetector:
    """Stateful detector for consecutive blank OCR pages."""

    def __init__(self, config: OCRGuardConfig) -> None:
        """Initialize with detection thresholds."""
        self.config = config
        self._current_blank_pages: list[Page] = []

    def is_page_blank(self, page: Page) -> bool:
        """Return whether a page has insufficient OCR text.

        A page is blank when it has no bubbles, or every bubble's OCR source text
        is shorter than ``min_text_length`` after stripping whitespace.
        """
        if not page.bubbles:
            return True

        min_length = self.config.min_text_length
        return all(len((bubble.source_text or "").strip()) < min_length for bubble in page.bubbles)

    def check_sequence(self, pages: list[Page]) -> BlankPageSequence | None:
        """Scan pages for consecutive blank sequences."""
        self.reset()
        threshold = self.config.consecutive_blank_threshold

        detected_pages: list[Page] | None = None
        for page in pages:
            if self.is_page_blank(page):
                self._current_blank_pages.append(page)
                continue

            if len(self._current_blank_pages) >= threshold:
                detected_pages = list(self._current_blank_pages)
                break
            self._current_blank_pages = []

        if detected_pages is None and len(self._current_blank_pages) >= threshold:
            detected_pages = list(self._current_blank_pages)

        if detected_pages is None:
            return None

        sequence = self._build_sequence(detected_pages)
        logger.warning(
            "Detected %d consecutive OCR-blank pages from %s to %s",
            sequence.blank_count,
            sequence.start_index,
            sequence.end_index,
        )
        return sequence

    def reset(self) -> None:
        """Clear internal state."""
        self._current_blank_pages = []

    def _build_sequence(self, blank_pages: list[Page]) -> BlankPageSequence:
        first = blank_pages[0]
        last = blank_pages[-1]
        return BlankPageSequence(
            start_index=int(first.page_index),
            end_index=int(last.page_index),
            page_ids=[page.page_id for page in blank_pages],
            blank_count=len(blank_pages),
        )
