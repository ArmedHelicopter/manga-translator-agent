"""Tests for learning extraction contracts."""

from __future__ import annotations

from mga.learning.dual_vision import analyze_manga_pair, analyze_novel_pair
from mga.learning.models import AlignedPageData, PagePair
from mga.learning.pattern_extractor import _aggregate_pages


class FakeNovelProvider:
    def chat_structured(self, messages, schema):
        return {
            "source_text": "おはよう",
            "translated_text": "早上好",
            "bubble_pairs": [
                {
                    "bubble_id": "b1",
                    "source_text": "おはよう",
                    "translated_text": "早上好",
                    "speaker_hint": "akari",
                    "speech_style": "polite",
                }
            ],
            "characters": [],
            "terminology": [],
            "speech_patterns": {},
            "style_notes": "natural",
        }


class FakeMangaProvider:
    def vision_structured(self, messages, images, schema):
        return {
            "source_text": "src",
            "translated_text": "tgt",
            "bubble_pairs": [],
            "characters": [],
            "terminology": [],
            "speech_patterns": {},
            "style_notes": "visual",
        }


def test_analyze_novel_pair_preserves_bubble_pairs(tmp_path):
    original = tmp_path / "chapter.txt"
    translated = tmp_path / "chapter.zh.txt"
    original.write_text("おはよう", encoding="utf-8")
    translated.write_text("早上好", encoding="utf-8")

    result = analyze_novel_pair(
        FakeNovelProvider(),
        PagePair(str(original), str(translated), "chapter"),
    )

    assert result is not None
    assert result.bubble_pairs[0]["bubble_id"] == "b1"
    assert result.bubble_pairs[0]["speaker_hint"] == "akari"


def test_pattern_aggregation_includes_bubble_level_alignment():
    page = AlignedPageData(
        page_id="p1",
        source_text="おはよう",
        translated_text="早上好",
        characters=[],
        terminology=[],
        speech_patterns={},
        style_notes="natural",
        bubble_pairs=[
            {
                "bubble_id": "b1",
                "source_text": "おはよう",
                "translated_text": "早上好",
            }
        ],
    )

    aggregated = _aggregate_pages([page])

    assert aggregated["bubble_pairs"] == [
        {
            "page_id": "p1",
            "bubble_id": "b1",
            "source_text": "おはよう",
            "translated_text": "早上好",
        }
    ]


def test_analyze_novel_pair_preserves_alignment_metadata(tmp_path):
    original = tmp_path / "chapter.txt"
    translated = tmp_path / "chapter.zh.txt"
    original.write_text("source", encoding="utf-8")
    translated.write_text("target", encoding="utf-8")

    result = analyze_novel_pair(
        FakeNovelProvider(),
        PagePair(
            str(original),
            str(translated),
            "chapter",
            alignment_status="visual-warning",
            alignment_score=0.5,
        ),
    )

    assert result is not None
    assert result.alignment_status == "visual-warning"
    assert result.alignment_score == 0.5


def test_analyze_manga_pair_preserves_alignment_metadata(tmp_path):
    original = tmp_path / "page.png"
    translated = tmp_path / "page.zh.png"
    original.write_bytes(b"original")
    translated.write_bytes(b"translated")

    result = analyze_manga_pair(
        FakeMangaProvider(),
        PagePair(
            str(original),
            str(translated),
            "page",
            alignment_status="visual-verified",
            alignment_score=1.0,
        ),
    )

    assert result is not None
    assert result.alignment_status == "visual-verified"
    assert result.alignment_score == 1.0


def test_pattern_aggregation_includes_alignment_metadata():
    page = AlignedPageData(
        page_id="p1",
        source_text="source",
        translated_text="target",
        characters=[],
        terminology=[],
        speech_patterns={},
        style_notes="natural",
        alignment_status="visual-verified",
        alignment_score=1.0,
    )

    aggregated = _aggregate_pages([page])

    assert aggregated["alignment"] == [
        {"page_id": "p1", "status": "visual-verified", "score": 1.0}
    ]
    assert aggregated["alignment_summary"] == {"visual-verified": 1}
