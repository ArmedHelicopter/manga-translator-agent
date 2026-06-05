"""Tests for mga.learning.pattern_extractor — LLM-based pattern extraction (Stage L3)."""

import pytest
from unittest.mock import MagicMock

from mga.learning.models import AlignedPageData, LearningResult
from mga.learning.pattern_extractor import extract_patterns


def _make_aligned_page(
    page_id: str = "page001",
    source_text: str = "original text",
    translated_text: str = "translated text",
    characters: list | None = None,
    terminology: list | None = None,
    speech_patterns: dict | None = None,
    style_notes: str = "",
    alignment_status: str = "filename-only",
    alignment_score: float = 0.0,
) -> AlignedPageData:
    return AlignedPageData(
        page_id=page_id,
        source_text=source_text,
        translated_text=translated_text,
        characters=characters or [],
        terminology=terminology or [],
        speech_patterns=speech_patterns or {},
        style_notes=style_notes,
        alignment_status=alignment_status,
        alignment_score=alignment_score,
    )


class TestExtractPatternsEmpty:
    def test_extract_patterns_empty(self):
        result = extract_patterns(None, [])

        assert isinstance(result, LearningResult)
        assert result.characters == []
        assert result.terms == []
        assert result.style_guide == {}
        assert result.character_graph == {}
        assert result.pages_processed == 0


class TestExtractPatternsMockProvider:
    def test_extract_patterns_mock_provider(self):
        provider = MagicMock()
        provider.chat_structured.return_value = {
            "characters": [
                {
                    "character_id": "taro",
                    "name_jp": "太郎",
                    "name_zh": "太郎",
                    "archetype": "热血少年",
                    "speech_patterns": {"自称": "我"},
                    "catchphrases": ["行くぞ！"],
                    "tone_spectrum": {"日常": "轻松"},
                    "translation_notes": {},
                },
            ],
            "terms": [
                {
                    "term_id": "bushido",
                    "term_jp": "武士道",
                    "term_zh": "武士道",
                    "context": "martial arts",
                    "cultural_weight": "high",
                    "strategy": "直译",
                    "frequency": 3,
                },
            ],
            "style_guide": {
                "literal_vs_free": 0.6,
                "honorific_handling": "保留",
                "punctuation_style": "standard",
                "dialog_style": "casual",
                "narrative_style": "formal",
                "key_decisions": ["kept honorifics"],
            },
            "character_graph": {
                "nodes": [{"id": "taro", "label": "太郎"}],
                "edges": [],
            },
        }

        pages = [
            _make_aligned_page(
                page_id="page001",
                characters=[{"name_jp": "太郎", "name_zh": "太郎"}],
                terminology=[{"term_jp": "武士道", "term_zh": "武士道"}],
            ),
        ]

        result = extract_patterns(provider, pages)

        assert isinstance(result, LearningResult)
        assert len(result.characters) == 1
        assert result.characters[0]["character_id"] == "taro"
        assert result.characters[0]["name_jp"] == "太郎"
        assert len(result.terms) == 1
        assert result.terms[0]["term_id"] == "bushido"
        assert result.style_guide["literal_vs_free"] == 0.6
        assert result.character_graph["nodes"][0]["id"] == "taro"
        assert result.pages_processed == 1
        provider.chat_structured.assert_called_once()

    def test_extract_patterns_multiple_pages(self):
        provider = MagicMock()
        provider.chat_structured.return_value = {
            "characters": [],
            "terms": [],
            "style_guide": {},
            "character_graph": {"nodes": [], "edges": []},
        }

        pages = [_make_aligned_page(page_id=f"page{i:03d}") for i in range(5)]

        result = extract_patterns(provider, pages)

        assert result.pages_processed == 5

    def test_extract_patterns_preserves_alignment_summary_on_result(self):
        provider = MagicMock()
        provider.chat_structured.return_value = {
            "characters": [],
            "terms": [],
            "style_guide": {},
            "character_graph": {"nodes": [], "edges": []},
        }

        result = extract_patterns(
            provider,
            [
                _make_aligned_page(
                    page_id="p1",
                    alignment_status="visual-verified",
                    alignment_score=1.0,
                ),
                _make_aligned_page(
                    page_id="p2",
                    alignment_status="filename-only",
                    alignment_score=0.0,
                ),
            ],
        )

        assert result.alignment_summary == {"visual-verified": 1, "filename-only": 1}
        assert result.alignment == [
            {"page_id": "p1", "status": "visual-verified", "score": 1.0},
            {"page_id": "p2", "status": "filename-only", "score": 0.0},
        ]

    def test_extract_patterns_schema_allows_relationship_speech(self):
        provider = MagicMock()
        provider.chat_structured.return_value = {
            "characters": [
                {
                    "character_id": "akari",
                    "name_jp": "Akari",
                    "name_zh": "Deng",
                    "relationship_speech": {
                        "ren": {
                            "honorific_level": "polite",
                            "self_ref": "boku",
                        },
                    },
                },
            ],
            "terms": [],
            "style_guide": {},
            "character_graph": {"nodes": [], "edges": []},
        }

        result = extract_patterns(provider, [_make_aligned_page(page_id="p001")])

        schema = provider.chat_structured.call_args.kwargs["schema"]
        character_props = schema["properties"]["characters"]["items"]["properties"]
        assert "relationship_speech" in character_props
        assert result.characters[0]["relationship_speech"]["ren"]["self_ref"] == "boku"

    def test_extract_patterns_prompt_includes_alignment_summary(self):
        provider = MagicMock()
        provider.chat_structured.return_value = {
            "characters": [],
            "terms": [],
            "style_guide": {},
            "character_graph": {"nodes": [], "edges": []},
        }

        extract_patterns(
            provider,
            [
                _make_aligned_page(
                    page_id="p1",
                    alignment_status="visual-verified",
                    alignment_score=1.0,
                ),
                _make_aligned_page(
                    page_id="p2",
                    alignment_status="visual-warning",
                    alignment_score=0.5,
                ),
            ],
        )

        content = provider.chat_structured.call_args.kwargs["messages"][0]["content"]
        assert '"alignment_summary"' in content
        assert '"visual-verified": 1' in content
        assert '"visual-warning": 1' in content


class TestExtractPatternsHeuristicFallback:
    def test_extract_patterns_heuristic_fallback(self):
        provider = MagicMock()
        provider.chat_structured.side_effect = RuntimeError("LLM unavailable")

        pages = [
            _make_aligned_page(
                page_id="page001",
                characters=[
                    {"name_jp": "太郎", "name_zh": "太郎", "speech_style": "casual"},
                ],
                terminology=[
                    {"term_jp": "武士道", "term_zh": "武士道", "context": "martial arts"},
                ],
                speech_patterns={"太郎": {"自称": "我"}},
                style_notes="Uses casual speech",
            ),
            _make_aligned_page(
                page_id="page002",
                characters=[
                    {"name_jp": "太郎", "name_zh": "太郎"},
                ],
                terminology=[
                    {"term_jp": "武士道", "term_zh": "武士道"},
                    {"term_jp": "侍", "term_zh": "武士"},
                ],
                style_notes="Formal narration",
            ),
        ]

        result = extract_patterns(provider, pages)

        assert isinstance(result, LearningResult)
        # Heuristic should merge characters by name_jp
        assert len(result.characters) == 1
        assert result.characters[0]["name_jp"] == "太郎"
        assert result.characters[0]["character_id"] == "太郎"
        # Terms should be deduplicated with frequency counted
        assert len(result.terms) == 2
        bushido = next(t for t in result.terms if t["term_jp"] == "武士道")
        assert bushido["frequency"] == 2
        samurai_term = next(t for t in result.terms if t["term_jp"] == "侍")
        assert samurai_term["frequency"] == 1
        # Style guide should have default heuristic values
        assert result.style_guide["literal_vs_free"] == 0.5
        assert result.style_guide["honorific_handling"] == "unknown"
        assert "Uses casual speech" in result.style_guide["raw_notes"]
        assert "Formal narration" in result.style_guide["raw_notes"]
        # Pages processed
        assert result.pages_processed == 2

    def test_extract_patterns_heuristic_preserves_alignment_summary(self):
        provider = MagicMock()
        provider.chat_structured.side_effect = RuntimeError("LLM unavailable")

        result = extract_patterns(
            provider,
            [
                _make_aligned_page(
                    page_id="p1",
                    alignment_status="visual-warning",
                    alignment_score=0.5,
                ),
            ],
        )

        assert result.alignment_summary == {"visual-warning": 1}
        assert result.alignment == [
            {"page_id": "p1", "status": "visual-warning", "score": 0.5}
        ]

    def test_extract_patterns_heuristic_deduplicates_style_notes(self):
        provider = MagicMock()
        provider.chat_structured.side_effect = RuntimeError("LLM unavailable")

        pages = [
            _make_aligned_page(style_notes="Same note"),
            _make_aligned_page(style_notes="Same note"),
            _make_aligned_page(style_notes="Different note"),
        ]

        result = extract_patterns(provider, pages)

        raw_notes = result.style_guide["raw_notes"]
        assert raw_notes.count("Same note") == 1
        assert "Different note" in raw_notes
