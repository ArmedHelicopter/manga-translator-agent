"""Tests for mga.learning.engine — pipeline orchestration."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from mga.learning.engine import LearningEngine
from mga.learning.models import AlignedPageData, LearningResult, PagePair
from mga.memory.state import StateManager


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
                terms=[{
                    "term_id": "bushido",
                    "term_jp": "武士道",
                    "term_zh": "武士道",
                    "strategy": "直译",
                    "context": "价值观",
                }],
                style_guide={"literal_vs_free": 0.5},
                character_graph={
                    "nodes": [{"id": "taro", "label": "太郎"}],
                    "edges": [],
                },
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
            assert (tmp_path / "style_guide.toml").exists()
            root_graph = tmp_path / "character_graph.json"
            assert root_graph.exists()
            root_graph_data = json.loads(root_graph.read_text(encoding="utf-8"))
            assert root_graph_data["nodes"][0]["id"] == "taro"
            assert (tmp_path / "terminology" / "learned.toml").exists()

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
            learned_terms = (tmp_path / "terminology" / "learned.toml").read_text(encoding="utf-8")
            assert "武士道" in learned_terms
            assert 'term_target = "武士道"' in learned_terms
            assert (tmp_path / "memory" / "state" / "character_graph.json").exists()

            # Verify combined learning result
            lr = json.loads((output_dir / "learning_result.json").read_text(encoding="utf-8"))
            assert lr["pages_processed"] == 1
            assert len(lr["characters"]) == 1
        finally:
            patch.stopall()

    def test_engine_writes_root_character_profile_toml(self, tmp_path):
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
                characters=[{
                    "character_id": "akari",
                    "name_jp": "Akari",
                    "name_zh": "Deng",
                    "archetype": "protagonist",
                    "speech_patterns": {"default": ["polite", "soft"]},
                    "catchphrases": ["I understand"],
                    "tone_spectrum": {"default": "calm"},
                    "translation_notes": {"addressing": "uses surnames"},
                    "confidence": 0.82,
                    "relationship_speech": {
                        "ren": {
                            "honorific_level": "polite",
                            "self_ref": "boku",
                            "address": "Sensei",
                            "required_terms": ["Sensei"],
                        }
                    },
                }],
                terms=[{
                    "term_id": "katana",
                    "term_jp": "katana",
                    "term_zh": "sword",
                    "strategy": "preserve",
                    "context": "weapon term",
                    "candidate_translations": ["sword", "blade"],
                    "accepted_reason": "Matches existing glossary.",
                    "rejected_reasons": {"blade": "Too generic for this work."},
                    "applicability_scope": "Use for named ritual weapons only.",
                }],
            )
            mock_validate.return_value = {
                "passed": True, "total_issues": 0, "errors": 0, "warnings": 0,
                "info": 0, "issues": [], "stats": {},
            }

            engine = LearningEngine(project_dir=tmp_path, provider=MagicMock())
            with patch.object(engine, "_seed_memory"):
                engine.learn(learn_dir=tmp_path / "learn")

            profile_toml = (tmp_path / "character_profiles" / "akari.toml").read_text(
                encoding="utf-8"
            )
            assert 'character_id = "akari"' in profile_toml
            assert 'name_jp = "Akari"' in profile_toml
            assert 'archetype = "protagonist"' in profile_toml
            assert 'default = "polite, soft"' in profile_toml
            assert '"I understand"' in profile_toml
            assert "[relationship_speech.ren]" in profile_toml
            assert 'honorific_level = "polite"' in profile_toml
            assert 'self_ref = "boku"' in profile_toml
            assert 'address = "Sensei"' in profile_toml
            assert 'required_terms = [' in profile_toml
            assert 'source = "learning_engine"' in profile_toml
            assert "confidence = 0.82" in profile_toml
            learned_terms = (tmp_path / "terminology" / "learned.toml").read_text(
                encoding="utf-8"
            )
            assert 'term_jp = "katana"' in learned_terms
            assert "confirmed = false" in learned_terms
            assert "pending_human_review = true" in learned_terms
            assert 'candidate_translations = [' in learned_terms
            assert 'accepted_reason = "Matches existing glossary."' in learned_terms
            assert "rejected_reasons" in learned_terms
            assert 'applicability_scope = "Use for named ritual weapons only."' in learned_terms
        finally:
            patch.stopall()

    def test_engine_preserves_explicit_profile_provenance_confidence(self, tmp_path):
        engine = LearningEngine(project_dir=tmp_path, provider=MagicMock())

        engine._write_character_profiles_toml(LearningResult(
            characters=[{
                "character_id": "akari",
                "name_jp": "Akari",
                "name_zh": "Deng",
                "confidence": 0.12,
                "provenance": {"confidence": 0.91, "last_reviewed_by": "editor"},
            }],
        ))

        profile_toml = (tmp_path / "character_profiles" / "akari.toml").read_text(
            encoding="utf-8"
        )
        assert "confidence = 0.91" in profile_toml
        assert "confidence = 0.12" not in profile_toml
        assert 'last_reviewed_by = "editor"' in profile_toml

    def test_engine_seeds_relationship_speech_to_memory_state(self, tmp_path):
        engine = LearningEngine(project_dir=tmp_path, provider=MagicMock())

        engine._seed_memory(LearningResult(
            characters=[
                {
                    "character_id": "akari",
                    "name_jp": "Akari",
                    "relationship_speech": {
                        "ren": {
                            "honorific_level": "polite",
                            "self_ref": "boku",
                            "address": "Sensei",
                        },
                    },
                },
            ],
        ))

        profile = StateManager.get_character(tmp_path, "akari")

        assert profile is not None
        assert profile.relationship_speech == {
            "ren": {
                "honorific_level": "polite",
                "self_ref": "boku",
                "address": "Sensei",
            },
        }

    def test_engine_seeds_character_provenance_to_memory_state(self, tmp_path):
        engine = LearningEngine(project_dir=tmp_path, provider=MagicMock())

        engine._seed_memory(LearningResult(
            characters=[
                {
                    "character_id": "akari",
                    "name_jp": "Akari",
                    "confidence": 0.12,
                    "provenance": {
                        "confidence": 0.91,
                        "last_reviewed_by": "editor",
                        "last_reviewed_chapter": 8,
                    },
                },
                {
                    "character_id": "ren",
                    "name_jp": "Ren",
                    "confidence": 0.44,
                },
            ],
        ))

        akari = StateManager.get_character(tmp_path, "akari")
        ren = StateManager.get_character(tmp_path, "ren")

        assert akari is not None
        assert ren is not None
        assert akari.provenance == {
            "source": "learning_engine",
            "confidence": 0.91,
            "last_reviewed_by": "editor",
            "last_reviewed_chapter": 8,
        }
        assert ren.provenance == {
            "source": "learning_engine",
            "confidence": 0.44,
        }

    def test_engine_seeds_learned_terms_as_pending_with_provenance(self, tmp_path):
        engine = LearningEngine(project_dir=tmp_path, provider=MagicMock())

        engine._seed_memory(LearningResult(
            terms=[
                {
                    "term_id": "glass_joining",
                    "term_jp": "硝子継ぎ",
                    "term_zh": "玻璃续接",
                    "context": "guild craft term",
                    "cultural_weight": "high",
                    "strategy": "preserve",
                    "frequency": 3,
                    "provenance": {
                        "page_id": "p001",
                        "bubble_id": "b1",
                    },
                },
            ],
        ))

        term = StateManager.get_term(tmp_path, "glass_joining")

        assert term is not None
        assert term.pending_human_review is True
        assert term.frequency == 3
        assert term.provenance == {
            "source": "learning_engine",
            "page_id": "p001",
            "bubble_id": "b1",
        }

    def test_engine_seeds_learned_term_review_fields_to_memory_state(self, tmp_path):
        engine = LearningEngine(project_dir=tmp_path, provider=MagicMock())

        engine._seed_memory(LearningResult(
            terms=[
                {
                    "term_id": "glass_joining",
                    "term_jp": "硝子継ぎ",
                    "term_zh": "玻璃续接",
                    "candidate_translations": ["玻璃续接", "水晶修补"],
                    "accepted_reason": "Matches the established ritual term.",
                    "rejected_reasons": {"水晶修补": "Sounds like a material repair."},
                    "applicability_scope": "Use only for the named repair art.",
                },
            ],
        ))

        term = StateManager.get_term(tmp_path, "glass_joining")

        assert term is not None
        assert term.candidate_translations == ["玻璃续接", "水晶修补"]
        assert term.accepted_reason == "Matches the established ritual term."
        assert term.rejected_reasons == {
            "水晶修补": "Sounds like a material repair.",
        }
        assert term.applicability_scope == "Use only for the named repair art."

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
