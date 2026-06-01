"""Tests for learning extraction contracts."""

from __future__ import annotations

from mga.learning.dual_vision import analyze_novel_pair
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
