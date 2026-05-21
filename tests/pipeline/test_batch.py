"""Tests for mga.pipeline.batch — BatchProcessor."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mga.pipeline.batch import BatchProcessor
from mga.pipeline.stages import PipelineContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chapter(chapter_id: str, input_path: str = "", output_path: str = "") -> dict:
    return {
        "chapter_id": chapter_id,
        "input_path": input_path or f"/input/{chapter_id}",
        "output_path": output_path or f"/output/{chapter_id}",
    }


def _completed_result(chapter_id: str) -> dict:
    return {
        "status": "completed",
        "chapter_id": chapter_id,
        "translations": 10,
        "errors": 0,
    }


def _make_context(translations: int = 10, errors: int = 0) -> PipelineContext:
    ctx = PipelineContext()
    ctx.translations = [MagicMock()] * translations
    ctx.errors = [{"stage": "x"}] * errors
    return ctx


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    d = tmp_path / "batch_project"
    d.mkdir()
    return d


@pytest.fixture
def processor(project_dir: Path) -> BatchProcessor:
    return BatchProcessor(project_dir, config=None, max_workers=1)


# ---------------------------------------------------------------------------
# Tests: Progress persistence
# ---------------------------------------------------------------------------


class TestProgressPersistence:
    """Progress file round-trip through _load_progress / _save_progress."""

    def test_load_progress_returns_empty_when_no_file(self, processor):
        assert processor._load_progress() == {}

    def test_save_and_load_roundtrip(self, processor):
        data = {"ch1": {"status": "completed"}}
        processor._save_progress(data)
        assert processor._load_progress() == data

    def test_load_progress_returns_empty_on_corrupt_file(self, processor):
        processor._progress_path.write_text("NOT JSON!!!", encoding="utf-8")
        assert processor._load_progress() == {}

    def test_update_progress_merges(self, processor):
        processor._save_progress({"ch1": {"status": "completed"}})
        processor._update_progress("ch2", {"status": "failed"})
        loaded = processor._load_progress()
        assert loaded["ch1"]["status"] == "completed"
        assert loaded["ch2"]["status"] == "failed"


# ---------------------------------------------------------------------------
# Tests: Sequential processing
# ---------------------------------------------------------------------------


class TestSequentialProcessing:
    """Single-worker batch processing."""

    @patch.object(BatchProcessor, "_process_single")
    def test_processes_all_chapters(self, mock_process, processor):
        mock_process.return_value = {"status": "completed", "translations": 5, "errors": 0}
        chapters = [_make_chapter("c1"), _make_chapter("c2")]
        summary = processor.process(chapters, resume=False)

        assert summary["total_chapters"] == 2
        assert summary["completed"] == 2
        assert mock_process.call_count == 2

    @patch.object(BatchProcessor, "_process_single")
    def test_resume_skips_completed(self, mock_process, processor):
        mock_process.return_value = {"status": "completed", "translations": 5, "errors": 0}
        # Pre-populate progress with c1 completed
        processor._save_progress({"c1": _completed_result("c1")})

        chapters = [_make_chapter("c1"), _make_chapter("c2")]
        summary = processor.process(chapters, resume=True)

        # Only c2 should be processed
        assert mock_process.call_count == 1
        assert summary["total_chapters"] == 2
        assert summary["completed"] == 2  # c1 from progress, c2 from processing

    @patch.object(BatchProcessor, "_process_single")
    def test_resume_false_reprocesses_all(self, mock_process, processor):
        mock_process.return_value = {"status": "completed", "translations": 5, "errors": 0}
        processor._save_progress({"c1": _completed_result("c1")})

        chapters = [_make_chapter("c1"), _make_chapter("c2")]
        summary = processor.process(chapters, resume=False)

        assert mock_process.call_count == 2

    @patch.object(BatchProcessor, "_process_single")
    def test_failed_chapter_recorded_in_parallel(self, mock_process, processor):
        """Exception handling only exists in the parallel (max_workers>1) path."""
        processor.max_workers = 2
        mock_process.side_effect = RuntimeError("boom")
        chapters = [_make_chapter("c1")]
        summary = processor.process(chapters, resume=False)

        assert summary["failed"] == 1
        assert "boom" in summary["results"]["c1"]["error"]


# ---------------------------------------------------------------------------
# Tests: Parallel processing
# ---------------------------------------------------------------------------


class TestParallelProcessing:
    """Multi-worker batch processing via ThreadPoolExecutor."""

    @patch.object(BatchProcessor, "_process_single")
    def test_parallel_processes_all(self, mock_process, processor):
        processor.max_workers = 4
        mock_process.return_value = {"status": "completed", "translations": 3, "errors": 0}
        chapters = [_make_chapter("c1"), _make_chapter("c2"), _make_chapter("c3")]
        summary = processor.process(chapters, resume=False)

        assert summary["total_chapters"] == 3
        assert mock_process.call_count == 3

    @patch.object(BatchProcessor, "_process_single")
    def test_parallel_failure_recorded(self, mock_process, processor):
        processor.max_workers = 2
        mock_process.side_effect = RuntimeError("crash")
        chapters = [_make_chapter("c1")]
        summary = processor.process(chapters, resume=False)

        assert summary["failed"] == 1


# ---------------------------------------------------------------------------
# Tests: get_pending_chapters / reset
# ---------------------------------------------------------------------------


class TestGetPendingChapters:
    def test_all_pending_when_no_progress(self, processor):
        chapters = [_make_chapter("a"), _make_chapter("b")]
        assert processor.get_pending_chapters(chapters) == chapters

    def test_filters_completed(self, processor):
        processor._save_progress({"a": _completed_result("a")})
        chapters = [_make_chapter("a"), _make_chapter("b")]
        pending = processor.get_pending_chapters(chapters)
        assert len(pending) == 1
        assert pending[0]["chapter_id"] == "b"

    def test_partial_not_filtered(self, processor):
        processor._save_progress({"a": {"status": "partial"}})
        chapters = [_make_chapter("a")]
        pending = processor.get_pending_chapters(chapters)
        assert len(pending) == 1


class TestReset:
    def test_removes_progress_file(self, processor):
        processor._save_progress({"x": _completed_result("x")})
        assert processor._progress_path.exists()
        processor.reset()
        assert not processor._progress_path.exists()

    def test_reset_when_no_file(self, processor):
        processor.reset()  # should not raise


# ---------------------------------------------------------------------------
# Tests: _build_summary
# ---------------------------------------------------------------------------


class TestBuildSummary:
    def test_summary_counts(self, processor):
        results = {
            "c1": {"status": "completed", "translations": 10, "errors": 0},
            "c2": {"status": "partial", "translations": 5, "errors": 2},
            "c3": {"status": "failed", "translations": 0, "errors": 1},
        }
        summary = processor._build_summary(results)
        assert summary["total_chapters"] == 3
        assert summary["completed"] == 1
        assert summary["partial"] == 1
        assert summary["failed"] == 1
        assert summary["total_translations"] == 15
        assert summary["total_errors"] == 3
