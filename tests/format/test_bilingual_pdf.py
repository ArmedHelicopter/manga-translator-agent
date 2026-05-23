"""Tests for mga.format.bilingual_pdf — create_bilingual_pdf."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from mga.format.bilingual_pdf import (
    _escape_xml,
    _create_fallback_pdf,
    create_bilingual_pdf,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bubble(bubble_id: str = "b1", source: str = "こんにちは", reading_order: int = 0):
    return SimpleNamespace(
        bubble_id=bubble_id,
        source_text=source,
        reading_order=reading_order,
        speaker_id=None,
        speaker_name=None,
    )


def _make_translation(bubble_id: str = "b1", text: str = "Hello"):
    return SimpleNamespace(bubble_id=bubble_id, text=text)


def _make_page(
    page_index: int = 0,
    page_id: str = "page_0",
    bubbles=None,
):
    return SimpleNamespace(
        page_id=page_id,
        page_index=page_index,
        bubbles=bubbles or [_make_bubble()],
    )


# ---------------------------------------------------------------------------
# Tests: _escape_xml
# ---------------------------------------------------------------------------


class TestEscapeXml:
    def test_escapes_ampersand(self):
        assert _escape_xml("A & B") == "A &amp; B"

    def test_escapes_angle_brackets(self):
        assert _escape_xml("<tag>") == "&lt;tag&gt;"

    def test_escapes_quotes(self):
        assert _escape_xml('"hello"') == "&quot;hello&quot;"

    def test_no_escape_plain_text(self):
        assert _escape_xml("plain text 123") == "plain text 123"

    def test_empty_string(self):
        assert _escape_xml("") == ""


# ---------------------------------------------------------------------------
# Tests: create_bilingual_pdf
# ---------------------------------------------------------------------------


class TestCreateBilingualPdf:
    """Integration-level tests using the fallback path (no reportlab dependency)."""

    def test_creates_output_directory(self, tmp_path: Path):
        pages = [_make_page()]
        translations = [_make_translation()]
        out = tmp_path / "sub" / "output.pdf"

        result = create_bilingual_pdf(pages, translations, out)
        assert result.exists()

    def test_fallback_returns_txt_file(self, tmp_path: Path):
        """Without reportlab, fallback produces a .txt file."""
        pages = [_make_page()]
        translations = [_make_translation()]
        out = tmp_path / "out.pdf"

        # Force ImportError for reportlab
        with patch.dict("sys.modules", {"reportlab": None, "reportlab.lib": None}):
            result = create_bilingual_pdf(pages, translations, out)

        assert result.suffix == ".txt"
        assert result.exists()

    def test_fallback_contains_source_text(self, tmp_path: Path):
        pages = [_make_page()]
        translations = [_make_translation()]
        out = tmp_path / "out.pdf"

        with patch.dict("sys.modules", {"reportlab": None, "reportlab.lib": None}):
            result = create_bilingual_pdf(pages, translations, out)

        content = result.read_text(encoding="utf-8")
        assert "こんにちは" in content
        assert "Hello" in content

    def test_fallback_empty_bubbles(self, tmp_path: Path):
        page = _make_page(bubbles=[])
        out = tmp_path / "out.pdf"

        with patch.dict("sys.modules", {"reportlab": None, "reportlab.lib": None}):
            result = create_bilingual_pdf([page], [], out)

        assert result.exists()
        content = result.read_text(encoding="utf-8")
        assert "共 1 页" in content

    def test_fallback_multiple_pages(self, tmp_path: Path):
        pages = [_make_page(page_index=0), _make_page(page_index=1, page_id="p1")]
        translations = [_make_translation(), _make_translation(bubble_id="b2")]
        out = tmp_path / "out.pdf"

        with patch.dict("sys.modules", {"reportlab": None, "reportlab.lib": None}):
            result = create_bilingual_pdf(pages, translations, out)

        content = result.read_text(encoding="utf-8")
        assert "页面 1" in content
        assert "页面 2" in content

    def test_fallback_missing_translation_uses_empty(self, tmp_path: Path):
        bubble = _make_bubble(bubble_id="b_missing")
        page = _make_page(bubbles=[bubble])
        out = tmp_path / "out.pdf"

        with patch.dict("sys.modules", {"reportlab": None, "reportlab.lib": None}):
            result = create_bilingual_pdf([page], [], out)

        content = result.read_text(encoding="utf-8")
        assert "译文: " in content  # empty translation


class TestReportlabPath:
    """Tests that exercise the reportlab code path via mocking."""

    @patch("mga.format.bilingual_pdf._create_pdf_with_reportlab")
    def test_reportlab_called_when_available(self, mock_rl, tmp_path: Path):
        pages = [_make_page()]
        translations = [_make_translation()]
        out = tmp_path / "out.pdf"
        mock_rl.return_value = out

        result = create_bilingual_pdf(pages, translations, out, title="Test Book")
        mock_rl.assert_called_once()
        assert result == out

    def test_reportlab_import_error_triggers_fallback(self, tmp_path: Path):
        pages = [_make_page()]
        translations = [_make_translation()]
        out = tmp_path / "out.pdf"

        # _create_pdf_with_reportlab will raise ImportError because reportlab isn't installed
        with patch("mga.format.bilingual_pdf._create_pdf_with_reportlab", side_effect=ImportError):
            result = create_bilingual_pdf(pages, translations, out)

        assert result.exists()


# ---------------------------------------------------------------------------
# Tests: _create_fallback_pdf directly
# ---------------------------------------------------------------------------


class TestCreateFallbackPdf:
    def test_custom_title(self, tmp_path: Path):
        out = tmp_path / "out.txt"
        result = _create_fallback_pdf([], [], out, title="My Manga")
        content = result.read_text(encoding="utf-8")
        assert "My Manga" in content

    def test_bubble_sorted_by_reading_order(self, tmp_path: Path):
        b1 = _make_bubble(bubble_id="b1", source="second", reading_order=1)
        b2 = _make_bubble(bubble_id="b2", source="first", reading_order=0)
        page = _make_page(bubbles=[b1, b2])
        trans_by_id = {
            "b1": _make_translation(bubble_id="b1", text="Second"),
            "b2": _make_translation(bubble_id="b2", text="First"),
        }
        out = tmp_path / "out.txt"
        result = _create_fallback_pdf([page], trans_by_id, out, title="Test")
        content = result.read_text(encoding="utf-8")
        # "first" should appear before "second" in output
        assert content.index("first") < content.index("second")

    def test_returns_txt_path(self, tmp_path: Path):
        out = tmp_path / "document.pdf"
        result = _create_fallback_pdf([], {}, out, title="Test")
        assert result.suffix == ".txt"
