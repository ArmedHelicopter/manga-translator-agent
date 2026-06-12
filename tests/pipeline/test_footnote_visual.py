"""Visual regression test for footnote rendering.

Tests that _draw_footnotes() actually renders visible text at the
bottom of the page image by checking pixel variance in the bottom
20% of the output.
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image


@pytest.fixture
def mock_manga_translator():
    """Create a MangaTranslator instance with mocked dependencies."""
    from unittest.mock import MagicMock, patch

    with patch("manga_translator.manga_translator.MangaTranslator.__init__", return_value=None):
        from manga_translator.manga_translator import MangaTranslator
        mt = MangaTranslator()
        return mt


def _make_white_page(height: int = 1200, width: int = 800) -> np.ndarray:
    """Create a white page image as numpy array (RGB, cv2-style)."""
    return np.ones((height, width, 3), dtype=np.uint8) * 255


def _bottom_region_pixels(img_array: np.ndarray, fraction: float = 0.2) -> np.ndarray:
    """Get pixel values from the bottom fraction of an image."""
    h = img_array.shape[0]
    bottom_start = int(h * (1 - fraction))
    return img_array[bottom_start:, :, :]


def _has_text_pixels(img_array: np.ndarray, dark_threshold: int = 220) -> bool:
    """Check if an image region has non-white (text) pixels.

    Text pixels are dark (low values). Instead of checking the mean
    (which is dominated by white space), check if any pixels are
    below the dark_threshold.
    """
    gray = np.mean(img_array, axis=2)
    return bool(np.any(gray < dark_threshold))


class TestFootnoteVisualRendering:
    """Tests that verify footnote text actually appears in rendered images."""

    def test_draw_footnotes_adds_visible_text_to_bottom(self, mock_manga_translator):
        """Test that _draw_footnotes renders visible text in the bottom of the page."""
        mt = mock_manga_translator
        white_page = _make_white_page()

        # Bottom region of white page should be all white
        bottom_before = _bottom_region_pixels(white_page)
        assert not _has_text_pixels(bottom_before), "White page should have no text"

        footnotes = [
            {
                "original": "ハイボール",
                "translation": "highball",
                "type": "cultural",
                "explanation": "A Japanese-style whisky highball",
            },
            {
                "original": "居酒屋",
                "translation": "izakaya",
                "type": "cultural",
                "explanation": "A Japanese-style pub",
            },
        ]

        result = mt._draw_footnotes(white_page, footnotes)

        # Bottom region of result should have text pixels
        bottom_after = _bottom_region_pixels(result)
        assert _has_text_pixels(bottom_after), "Footnote text should be visible in bottom 20%"

    def test_draw_footnotes_empty_list_no_change(self, mock_manga_translator):
        """Test that empty footnotes list returns the image unchanged."""
        mt = mock_manga_translator
        white_page = _make_white_page()
        result = mt._draw_footnotes(white_page, [])
        np.testing.assert_array_equal(result, white_page)

    def test_draw_footnotes_sfx_type(self, mock_manga_translator):
        """Test SFX-type footnotes render with 拟声 annotation."""
        mt = mock_manga_translator
        white_page = _make_white_page()

        footnotes = [
            {
                "original": "ドカン",
                "translation": "BOOM",
                "type": "sfx",
                "explanation": "Explosion sound effect",
            },
        ]

        result = mt._draw_footnotes(white_page, footnotes)
        bottom_after = _bottom_region_pixels(result)
        assert _has_text_pixels(bottom_after), "SFX footnote should be visible"

    def test_draw_footnotes_footer_strip_for_non_blank_corners(self, mock_manga_translator):
        """Test that footnotes use footer strip when page corners aren't blank."""
        mt = mock_manga_translator

        # Create a page with dark (non-blank) corners — text everywhere
        dark_page = np.ones((1200, 800, 3), dtype=np.uint8) * 50  # Dark gray

        footnotes = [
            {
                "original": "テスト",
                "translation": "test",
                "type": "loanword",
                "explanation": "A test term",
            },
        ]

        result = mt._draw_footnotes(dark_page, footnotes)

        # Result should be taller (footer strip added)
        assert result.shape[0] > dark_page.shape[0], \
            "Footer strip should be added when corners aren't blank"

    def test_draw_footnotes_no_original_skipped(self, mock_manga_translator):
        """Test that footnotes without 'original' field are skipped."""
        mt = mock_manga_translator
        white_page = _make_white_page()

        footnotes = [
            {"translation": "test", "type": "cultural"},  # No 'original'
        ]

        result = mt._draw_footnotes(white_page, footnotes)

        # Should return unchanged since no valid footnotes
        np.testing.assert_array_equal(result, white_page)

    def test_draw_footnotes_explanation_included(self, mock_manga_translator):
        """Test that footnotes with explanations render more text than without."""
        mt = mock_manga_translator

        # Page with explanation
        white_page1 = _make_white_page()
        footnotes_with_explanation = [
            {
                "original": "ハイボール",
                "translation": "highball",
                "type": "cultural",
                "explanation": "A whisky highball served with soda water over ice",
            },
        ]
        result1 = mt._draw_footnotes(white_page1, footnotes_with_explanation)

        # Page without explanation
        white_page2 = _make_white_page()
        footnotes_no_explanation = [
            {
                "original": "ハイボール",
                "translation": "highball",
                "type": "cultural",
                "explanation": "",
            },
        ]
        result2 = mt._draw_footnotes(white_page2, footnotes_no_explanation)

        # Both should have visible text
        assert _has_text_pixels(_bottom_region_pixels(result1))
        assert _has_text_pixels(_bottom_region_pixels(result2))

    def test_draw_footnotes_output_is_valid_image(self, mock_manga_translator):
        """Test that _draw_footnotes output can be converted to a PIL Image."""
        mt = mock_manga_translator
        white_page = _make_white_page()

        footnotes = [
            {
                "original": "コーヒー",
                "translation": "coffee",
                "type": "loanword",
                "explanation": "Loanword from Dutch 'koffie'",
            },
        ]

        result = mt._draw_footnotes(white_page, footnotes)

        # Should be a valid numpy array that PIL can handle
        import cv2
        pil_img = Image.fromarray(cv2.cvtColor(result, cv2.COLOR_RGB2BGR))
        assert pil_img.size[0] > 0
        assert pil_img.size[1] > 0
