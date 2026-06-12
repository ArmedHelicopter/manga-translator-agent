"""Tests for page-level footnote compilation."""

from __future__ import annotations

import pytest

from mga.models.page import Page, PageFootnote, Bubble, BoundingBox
from mga.models.translation import TranslationCandidate, FootnoteEntry
from mga.pipeline.page_footnotes import (
    PageFootnoteService,
    get_page_footnote_service,
    CULTURAL_REFERENCES,
    FICTIONAL_REFERENCES,
    detect_footnote_terms,
    ALL_CULTURAL_DB,
)


class TestPageFootnoteService:
    """Tests for PageFootnoteService."""

    def test_compile_page_footnotes_empty(self):
        """Test compilation with no bubbles/translations."""
        service = PageFootnoteService()
        page_footnotes = service.compile_page_footnotes(
            bubbles=[],
            translations=[],
        )
        assert page_footnotes == []

    def test_compile_page_footnotes_single_bubble(self):
        """Test compilation with single bubble."""
        bubble = Bubble(
            bubble_id="bubble_1",
            source_text="居酒屋で飲む",
            bbox=BoundingBox(x=10, y=10, width=100, height=50),
        )
        trans = TranslationCandidate(
            bubble_id="bubble_1",
            text="在居酒屋喝酒",
            footnotes=[
                FootnoteEntry(
                    original="居酒屋",
                    translation="居酒屋",
                    type="cultural",
                    explanation="日本传统小酒馆",
                ),
            ],
        )

        service = PageFootnoteService()
        page_footnotes = service.compile_page_footnotes(
            bubbles=[bubble],
            translations=[trans],
        )

        assert len(page_footnotes) == 1
        assert page_footnotes[0].term == "居酒屋"
        assert page_footnotes[0].type == "cultural"
        assert page_footnotes[0].explanation == "日本传统小酒馆"
        assert page_footnotes[0].index == 1

    def test_compile_page_footnotes_deduplication(self):
        """Test that duplicate terms are deduplicated."""
        bubble1 = Bubble(
            bubble_id="bubble_1",
            source_text="居酒屋是个好地方",
            bbox=BoundingBox(x=10, y=10, width=100, height=50),
        )
        bubble2 = Bubble(
            bubble_id="bubble_2",
            source_text="居酒屋在那边",
            bbox=BoundingBox(x=10, y=70, width=100, height=50),
        )
        trans1 = TranslationCandidate(
            bubble_id="bubble_1",
            text="居酒屋是个好地方",
            footnotes=[
                FootnoteEntry(original="居酒屋", translation="居酒屋", type="cultural"),
            ],
        )
        trans2 = TranslationCandidate(
            bubble_id="bubble_2",
            text="居酒屋在那边",
            footnotes=[
                FootnoteEntry(original="居酒屋", translation="居酒屋", type="cultural"),
            ],
        )

        service = PageFootnoteService()
        page_footnotes = service.compile_page_footnotes(
            bubbles=[bubble1, bubble2],
            translations=[trans1, trans2],
        )

        # Should only have one entry for "居酒屋"
        assert len(page_footnotes) == 1
        assert page_footnotes[0].term == "居酒屋"

    def test_compile_page_footnotes_ordering(self):
        """Test that footnotes are ordered by first appearance."""
        bubble1 = Bubble(
            bubble_id="bubble_1",
            source_text="居酒屋",
            bbox=BoundingBox(x=10, y=10, width=100, height=50),
        )
        bubble2 = Bubble(
            bubble_id="bubble_2",
            source_text="スキル",
            bbox=BoundingBox(x=10, y=70, width=100, height=50),
        )
        bubble3 = Bubble(
            bubble_id="bubble_3",
            source_text="ハイボール",
            bbox=BoundingBox(x=10, y=130, width=100, height=50),
        )
        trans1 = TranslationCandidate(
            bubble_id="bubble_1",
            text="居酒屋",
            footnotes=[
                FootnoteEntry(original="居酒屋", translation="居酒屋", type="cultural"),
            ],
        )
        trans2 = TranslationCandidate(
            bubble_id="bubble_2",
            text="技能",
            footnotes=[
                FootnoteEntry(original="スキル", translation="技能", type="fictional"),
            ],
        )
        trans3 = TranslationCandidate(
            bubble_id="bubble_3",
            text="高球",
            footnotes=[
                FootnoteEntry(original="ハイボール", translation="高球", type="cultural"),
            ],
        )

        service = PageFootnoteService()
        page_footnotes = service.compile_page_footnotes(
            bubbles=[bubble1, bubble2, bubble3],
            translations=[trans1, trans2, trans3],
        )

        assert len(page_footnotes) == 3
        assert page_footnotes[0].index == 1
        assert page_footnotes[0].term == "居酒屋"
        assert page_footnotes[1].index == 2
        assert page_footnotes[1].term == "スキル"
        assert page_footnotes[2].index == 3
        assert page_footnotes[2].term == "ハイボール"

    def test_compile_page_footnotes_db_explanation(self):
        """Test that database explanations are used when no explanation provided."""
        bubble = Bubble(
            bubble_id="bubble_1",
            source_text="ハイボールを飲む",
            bbox=BoundingBox(x=10, y=10, width=100, height=50),
        )
        # No explanation provided - should use database
        trans = TranslationCandidate(
            bubble_id="bubble_1",
            text="喝高球",
            footnotes=[
                FootnoteEntry(original="ハイボール", translation="高球", type="cultural"),
            ],
        )

        service = PageFootnoteService()
        page_footnotes = service.compile_page_footnotes(
            bubbles=[bubble],
            translations=[trans],
        )

        assert len(page_footnotes) == 1
        # Should have database explanation
        assert "Highball" in page_footnotes[0].explanation
        assert "威士忌" in page_footnotes[0].explanation

    def test_compile_page_footnotes_source_bubble_id(self):
        """Test that source bubble ID is tracked."""
        bubble = Bubble(
            bubble_id="bubble_1",
            source_text="テスト",
            bbox=BoundingBox(x=10, y=10, width=100, height=50),
        )
        trans = TranslationCandidate(
            bubble_id="bubble_1",
            text="测试",
            footnotes=[
                FootnoteEntry(original="テスト", translation="测试", type="loanword"),
            ],
        )

        service = PageFootnoteService()
        page_footnotes = service.compile_page_footnotes(
            bubbles=[bubble],
            translations=[trans],
        )

        assert len(page_footnotes) == 1
        assert page_footnotes[0].source_bubble_id == "bubble_1"


class TestDetectFootnoteTerms:
    """Tests for footnote term detection."""

    def test_detect_katakana_loanword(self):
        """Test detection of katakana loanwords."""
        text = "コーヒーを飲む"
        detected = detect_footnote_terms(text)
        terms = [t[0] for t in detected]
        assert "コーヒー" in terms

    def test_detect_cultural_term(self):
        """Test detection of cultural terms."""
        text = "居酒屋で飲む"
        detected = detect_footnote_terms(text)
        terms = [t[0] for t in detected]
        assert "居酒屋" in terms

    def test_detect_fictional_term(self):
        """Test detection of fictional/game terms."""
        text = "スキルを使う"
        detected = detect_footnote_terms(text)
        terms = [t[0] for t in detected]
        assert "スキル" in terms

    def test_detect_multiple_terms(self):
        """Test detection of multiple terms."""
        text = "居酒屋でハイボールを飲んで、スキルを上げた"
        detected = detect_footnote_terms(text)
        terms = [t[0] for t in detected]
        assert "居酒屋" in terms
        assert "ハイボール" in terms
        assert "スキル" in terms


class TestCulturalDatabase:
    """Tests for cultural reference database."""

    def test_cultural_references_has_highball(self):
        """Test that highball is in cultural references."""
        assert "ハイボール" in CULTURAL_REFERENCES
        info = CULTURAL_REFERENCES["ハイボール"]
        assert info["type"] == "cultural"
        assert "威士忌" in info["explanation"]

    def test_cultural_references_has_izakaya(self):
        """Test that izakaya is in cultural references."""
        assert "居酒屋" in CULTURAL_REFERENCES
        info = CULTURAL_REFERENCES["居酒屋"]
        assert info["type"] == "cultural"

    def test_fictional_references_has_skill(self):
        """Test that skill is in fictional references."""
        assert "スキル" in FICTIONAL_REFERENCES
        info = FICTIONAL_REFERENCES["スキル"]
        assert info["type"] == "fictional"

    def test_all_db_has_common_terms(self):
        """Test that all DB covers common manga terms."""
        common_terms = [
            "居酒屋",
            "ハイボール",
            "スキル",
            "魔法",
            "勇者",
            "レベル",
            "神社",
            "お盆",
        ]
        for term in common_terms:
            assert term in ALL_CULTURAL_DB, f"Missing term: {term}"


class TestPageFootnoteModel:
    """Tests for PageFootnote model."""

    def test_page_footnote_creation(self):
        """Test PageFootnote model creation."""
        pf = PageFootnote(
            index=1,
            term="テスト",
            translation="测试",
            explanation="测试说明",
            type="loanword",
            source_bubble_id="bubble_1",
        )
        assert pf.index == 1
        assert pf.term == "テスト"
        assert pf.translation == "测试"
        assert pf.explanation == "测试说明"
        assert pf.type == "loanword"
        assert pf.source_bubble_id == "bubble_1"

    def test_page_footnotes_on_page_model(self):
        """Test Page model with page_footnotes."""
        bubble = Bubble(
            bubble_id="bubble_1",
            source_text="テスト",
            bbox=BoundingBox(x=10, y=10, width=100, height=50),
        )
        footnote = PageFootnote(
            index=1,
            term="テスト",
            translation="测试",
            explanation="测试",
            type="loanword",
        )
        page = Page(
            page_id="page_1",
            bubbles=[bubble],
            page_footnotes=[footnote],
        )
        assert len(page.page_footnotes) == 1
        assert page.page_footnotes[0].term == "テスト"