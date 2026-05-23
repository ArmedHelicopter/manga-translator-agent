"""Tests for mga.pipeline.incremental — IncrementalTranslator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mga.models import Bubble, Page, TranslationCandidate
from mga.pipeline.incremental import IncrementalTranslator, incremental_translate
from mga.pipeline.stages import PipelineContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(
    *,
    translations: list[TranslationCandidate] | None = None,
    pages: list[Page] | None = None,
    errors: list[dict] | None = None,
) -> PipelineContext:
    ctx = PipelineContext()
    ctx.translations = translations or []
    ctx.pages = pages or []
    ctx.errors = errors or []
    return ctx


def _make_page_with_speaker(
    page_index: int = 0,
    speaker: str = "tanaka",
    source: str = "すごいね。",
    bubble_id: str = "b0",
) -> Page:
    return Page(
        page_index=page_index,
        bubbles=[
            Bubble(
                bubble_id=bubble_id,
                speaker_id=speaker,
                speaker_name=speaker,
                source_text=source,
            )
        ],
    )


def _make_candidate(bubble_id: str = "b0", text: str = "Amazing!") -> TranslationCandidate:
    return TranslationCandidate(bubble_id=bubble_id, text=text)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    d = tmp_path / "project"
    d.mkdir()
    return d


@pytest.fixture
def translator(project_dir: Path) -> IncrementalTranslator:
    return IncrementalTranslator(project_dir, config=None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTranslateChapter:
    """translate_chapter orchestrates load -> pipeline -> update -> save."""

    @patch("mga.pipeline.incremental.PipelineOrchestrator")
    def test_returns_pipeline_context(self, MockOrchestrator, translator, project_dir):
        ctx = _make_context()
        MockOrchestrator.return_value.run.return_value = ctx

        result = translator.translate_chapter(
            input_path=project_dir / "ch1",
            output_path=project_dir / "out1",
            chapter_id="ch1",
        )
        assert result is ctx

    @patch("mga.pipeline.incremental.PipelineOrchestrator")
    def test_calls_orchestrator_with_correct_args(self, MockOrchestrator, translator, project_dir):
        ctx = _make_context()
        MockOrchestrator.return_value.run.return_value = ctx

        in_p = project_dir / "input"
        out_p = project_dir / "output"
        translator.translate_chapter(in_p, out_p, "ch1")

        MockOrchestrator.return_value.run.assert_called_once_with(
            str(in_p), str(out_p), None,
        )

    @patch("mga.pipeline.incremental.PipelineOrchestrator")
    def test_update_profiles_called_with_context(self, MockOrchestrator, translator, project_dir):
        """_update_profiles is called even when there are no translations (early return inside)."""
        ctx = _make_context()
        MockOrchestrator.return_value.run.return_value = ctx

        with patch.object(translator, "_update_profiles") as mock_update:
            translator.translate_chapter(project_dir / "in", project_dir / "out", "ch1")
            mock_update.assert_called_once_with(ctx, "ch1")

    @patch("mga.pipeline.incremental.PipelineOrchestrator")
    def test_save_state_called(self, MockOrchestrator, translator, project_dir):
        ctx = _make_context()
        MockOrchestrator.return_value.run.return_value = ctx

        with patch.object(translator, "_save_state") as mock_save:
            translator.translate_chapter(project_dir / "in", project_dir / "out")
            mock_save.assert_called_once()


class TestLoadPreviousContext:
    """_load_previous_context is a no-op that allows StateManager to load on demand."""

    def test_does_not_raise(self, translator):
        translator._load_previous_context()  # smoke test


class TestUpdateProfiles:
    """_update_profiles processes translations grouped by speaker."""

    def test_no_translations_exits_early(self, translator):
        ctx = _make_context(translations=[])
        translator._update_profiles(ctx, "ch1")  # should not raise

    @patch("mga.memory.evolution_tracker.EvolutionTracker")
    @patch("mga.memory.profile_builder.build_and_save_profile")
    def test_groups_translations_by_speaker(self, mock_builder, MockTracker, translator, project_dir):
        page = _make_page_with_speaker(speaker="tanaka", source="すごいね。", bubble_id="b1")
        candidate = _make_candidate(bubble_id="b1", text="Amazing!")
        ctx = _make_context(translations=[candidate], pages=[page])

        tracker_instance = MockTracker.return_value
        tracker_instance.detect_changes.return_value = None

        translator._update_profiles(ctx, "ch1")

        mock_builder.assert_called_once_with(
            project_dir,
            character_id="tanaka",
            name_jp="tanaka",
        )

    @patch("mga.memory.evolution_tracker.EvolutionTracker")
    @patch("mga.memory.profile_builder.build_and_save_profile")
    def test_bubble_without_speaker_is_skipped(self, mock_builder, MockTracker, translator):
        bubble = Bubble(bubble_id="b1", source_text="hello")
        page = Page(bubbles=[bubble])
        candidate = _make_candidate(bubble_id="b1", text="world")
        ctx = _make_context(translations=[candidate], pages=[page])

        translator._update_profiles(ctx, "ch1")
        mock_builder.assert_not_called()

    @patch("mga.memory.evolution_tracker.EvolutionTracker")
    @patch("mga.memory.profile_builder.build_and_save_profile")
    def test_translation_not_in_any_bubble_is_skipped(self, mock_builder, MockTracker, translator):
        candidate = _make_candidate(bubble_id="nonexistent", text="orphan")
        ctx = _make_context(translations=[candidate], pages=[])

        translator._update_profiles(ctx, "ch1")
        mock_builder.assert_not_called()


class TestSaveState:
    """_save_state loads and saves the character graph."""

    @patch("mga.memory.graph.CharacterGraph")
    def test_saves_graph(self, MockGraph, translator, project_dir):
        instance = MockGraph.load.return_value
        translator._save_state()
        instance.save.assert_called_once_with(project_dir)

    @patch("mga.memory.graph.CharacterGraph")
    def test_handles_graph_load_failure(self, MockGraph, translator):
        MockGraph.load.side_effect = RuntimeError("no graph")
        translator._save_state()  # should not raise


class TestCountHelpers:
    """_count_characters and _count_terms return 0 on failure."""

    @patch("mga.memory.state.StateManager")
    def test_count_characters(self, MockSM, translator, project_dir):
        MockSM.list_characters.return_value = ["a", "b"]
        assert translator._count_characters() == 2

    @patch("mga.memory.state.StateManager")
    def test_count_characters_error(self, MockSM, translator):
        MockSM.list_characters.side_effect = RuntimeError
        assert translator._count_characters() == 0

    @patch("mga.memory.state.StateManager")
    def test_count_terms(self, MockSM, translator, project_dir):
        MockSM.list_terms.return_value = ["t1"]
        assert translator._count_terms() == 1

    @patch("mga.memory.state.StateManager")
    def test_count_terms_error(self, MockSM, translator):
        MockSM.list_terms.side_effect = RuntimeError
        assert translator._count_terms() == 0


class TestConvenienceFunction:
    """incremental_translate is a thin wrapper around IncrementalTranslator."""

    @patch("mga.pipeline.incremental.PipelineOrchestrator")
    def test_delegates_to_translator(self, MockOrchestrator, project_dir):
        ctx = _make_context()
        MockOrchestrator.return_value.run.return_value = ctx

        result = incremental_translate(
            project_dir,
            project_dir / "in",
            project_dir / "out",
            config="cfg",
            chapter_id="c1",
        )
        assert result is ctx
