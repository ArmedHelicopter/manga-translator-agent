"""Tests for mga.learning.engine — pipeline orchestration."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from mga.learning.engine import LearningEngine
from mga.learning.models import AlignedPageData, LearningResult, PagePair


def _mock_stages():
    """Set up mocks for all pipeline stages and return them."""
    mock_align = patch("mga.learning.engine.align").start()
    mock_analyze = patch("mga.learning.engine.analyze_pairs").start()
    mock_extract = patch("mga.learning.engine.extract_patterns").start()
    mock_validate = patch("mga.learning.engine.validate").start()
    return mock_align, mock_analyze, mock_extract, mock_validate


class TestEngineLearnMock:
    def test_engine_learn_mock(self, tmp_path):
        mock_align, mock_analyze, mock_extract, mock_validate = _mock_stages()
        try:
            mock_align.return_value = [
                PagePair(
                    original_path="/orig/page001.png",
                    translated_path="/trans/page001.png",
                    page_id="page001",
                ),
            ]
            mock_analyze.return_value = [
                AlignedPageData(
                    page_id="page001",
                    source_text="original",
                    translated_text="translated",
                    characters=[{"name_jp": "太郎", "name_zh": "太郎"}],
                    terminology=[{"term_jp": "武士道", "term_zh": "武士道"}],
                    speech_patterns={"太郎": {"自称": "我"}},
                    style_notes="casual",
                ),
            ]
            mock_extract.return_value = LearningResult(
                characters=[{"character_id": "taro", "name_jp": "太郎", "name_zh": "太郎"}],
                terms=[{"term_id": "bushido", "term_jp": "武士道", "term_zh": "武士道"}],
                style_guide={"literal_vs_free": 0.5},
                character_graph={"nodes": [], "edges": []},
                pages_processed=1,
            )
            mock_validate.return_value = {
                "passed": True,
                "total_issues": 0,
                "errors": 0,
                "warnings": 0,
                "info": 0,
                "issues": [],
                "stats": {"characters_count": 1, "terms_count": 1},
            }

            provider = MagicMock()
            engine = LearningEngine(project_dir=tmp_path, provider=provider)
            with patch.object(engine, "_seed_memory"):
                result = engine.learn(learn_dir=tmp_path / "learn", mode="manga")

            # Verify pipeline stages were called
            mock_align.assert_called_once()
            mock_analyze.assert_called_once()
            mock_extract.assert_called_once()
            mock_validate.assert_called_once()

            # Verify result
            assert isinstance(result, LearningResult)
            assert len(result.characters) == 1
            assert len(result.terms) == 1
            assert result.quality_report["passed"] is True

            # Verify outputs were written
            output_dir = tmp_path / "memory" / "learned"
            assert output_dir.exists()
            assert (output_dir / "learning_result.json").exists()
            assert (output_dir / "quality_report.json").exists()
            assert (output_dir / "character_graph.json").exists()
            assert (output_dir / "style_guide.toml").exists()

            # Verify character profile file
            chars_dir = output_dir / "character_profiles"
            assert chars_dir.exists()
            assert (chars_dir / "taro.json").exists()
            char_data = json.loads((chars_dir / "taro.json").read_text(encoding="utf-8"))
            assert char_data["name_jp"] == "太郎"

            # Verify terminology file
            terms_dir = output_dir / "terminology"
            assert terms_dir.exists()
            assert (terms_dir / "bushido.json").exists()
            term_data = json.loads((terms_dir / "bushido.json").read_text(encoding="utf-8"))
            assert term_data["term_jp"] == "武士道"

            # Verify combined learning result
            lr = json.loads((output_dir / "learning_result.json").read_text(encoding="utf-8"))
            assert lr["pages_processed"] == 1
            assert len(lr["characters"]) == 1
        finally:
            patch.stopall()

    def test_engine_empty_pairs(self, tmp_path):
        mock_align, mock_analyze, mock_extract, mock_validate = _mock_stages()
        try:
            mock_align.return_value = []

            provider = MagicMock()
            engine = LearningEngine(project_dir=tmp_path, provider=provider)
            with patch.object(engine, "_seed_memory"):
                result = engine.learn(learn_dir=tmp_path / "learn")

            assert isinstance(result, LearningResult)
            assert result.characters == []
            assert result.terms == []
            assert result.pages_processed == 0

            # Later stages should not be called
            mock_analyze.assert_not_called()
            mock_extract.assert_not_called()
            mock_validate.assert_not_called()
        finally:
            patch.stopall()

    def test_engine_writes_style_guide_toml(self, tmp_path):
        mock_align, mock_analyze, mock_extract, mock_validate = _mock_stages()
        try:
            mock_align.return_value = [
                PagePair(original_path="/o/p1.png", translated_path="/t/p1.png", page_id="p1"),
            ]
            mock_analyze.return_value = [
                AlignedPageData(
                    page_id="p1", source_text="s", translated_text="t",
                    characters=[], terminology=[], speech_patterns={}, style_notes="",
                ),
            ]
            mock_extract.return_value = LearningResult(
                style_guide={
                    "literal_vs_free": 0.7,
                    "honorific_handling": "保留",
                    "punctuation_style": "standard",
                    "dialog_style": "casual",
                    "narrative_style": "formal",
                    "key_decisions": ["kept honorifics"],
                    "raw_notes": ["should be stripped from TOML"],
                },
            )
            mock_validate.return_value = {
                "passed": True, "total_issues": 0, "errors": 0, "warnings": 0,
                "info": 0, "issues": [], "stats": {},
            }

            engine = LearningEngine(project_dir=tmp_path, provider=MagicMock())
            with patch.object(engine, "_seed_memory"):
                engine.learn(learn_dir=tmp_path / "learn")

            toml_path = tmp_path / "memory" / "learned" / "style_guide.toml"
            assert toml_path.exists()
            content = toml_path.read_text(encoding="utf-8")
            assert "literal_vs_free" in content
            assert "raw_notes" not in content  # raw_notes should be stripped
        finally:
            patch.stopall()
