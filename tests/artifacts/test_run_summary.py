"""Tests for RunSummary build and write."""

import json
from dataclasses import asdict

from mga.artifacts.run_summary import RunSummary, build_run_summary, write_run_summary
from mga.artifacts.store import ArtifactStore
from mga.models import ProjectConfig, TranslationCandidate, Bubble, Page
from mga.pipeline.stages import PipelineContext


def _make_context(**overrides) -> PipelineContext:
    ctx = PipelineContext()
    ctx.pages = overrides.get("pages", [])
    ctx.translations = overrides.get("translations", [])
    ctx.qa_report = overrides.get("qa_report", {})
    ctx.errors = overrides.get("errors", [])
    ctx.metadata = overrides.get("metadata", {})
    ctx.artifacts = overrides.get("artifacts", {})
    return ctx


def _make_config(**overrides) -> ProjectConfig:
    defaults = {
        "source_lang": "ja",
        "target_lang": "zh-CN",
        "pipeline_mode": "manga",
        "input_format": "images",
        "output_format": "images",
    }
    defaults.update(overrides)
    return ProjectConfig(**defaults)


def test_build_run_summary_basic():
    ctx = _make_context(
        pages=[Page(page_id="p1", page_index=0), Page(page_id="p2", page_index=1)],
        translations=[
            TranslationCandidate(bubble_id="b1", text="hello", confidence=0.9),
            TranslationCandidate(bubble_id="b2", text="world", confidence=0.8),
        ],
        metadata={"stage_timings": {"vision": 1.5}, "total_duration": 3.0, "input_path": "/in", "output_path": "/out"},
    )
    cfg = _make_config()
    summary = build_run_summary(ctx, cfg)

    assert summary.status == "completed"
    assert summary.page_count == 2
    assert summary.translation_count == 2
    assert summary.pipeline_mode == "manga"
    assert summary.source_lang == "ja"
    assert summary.target_lang == "zh-CN"
    assert summary.stage_timings == {"vision": 1.5}
    assert summary.total_duration == 3.0
    assert summary.input_path == "/in"
    assert summary.output_path == "/out"
    assert summary.timestamp  # non-empty


def test_build_run_summary_status_partial():
    ctx = _make_context(errors=[{"stage": "format", "error": "bad input"}])
    cfg = _make_config()
    summary = build_run_summary(ctx, cfg)
    assert summary.status == "partial"
    assert summary.error_count == 1


def test_build_run_summary_status_failed():
    ctx = _make_context(errors=[{"stage": "translation", "error": "api timeout"}])
    cfg = _make_config()
    summary = build_run_summary(ctx, cfg)
    assert summary.status == "failed"


def test_run_summary_schema():
    summary = RunSummary()
    d = asdict(summary)
    required = [
        "timestamp", "pipeline_mode", "source_lang", "target_lang", "provider",
        "input_path", "output_path", "input_format", "output_format",
        "page_count", "translation_count", "stages_completed", "stage_timings",
        "total_duration", "error_count", "errors", "status",
    ]
    for field in required:
        assert field in d, f"Missing field: {field}"


def test_write_run_summary(tmp_path):
    store = ArtifactStore(tmp_path)
    summary = RunSummary(
        timestamp="2026-01-01T00:00:00Z",
        pipeline_mode="novel",
        page_count=10,
        status="completed",
    )
    rel = write_run_summary(store, summary)
    assert rel == "run.json"
    content = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert content["pipeline_mode"] == "novel"
    assert content["page_count"] == 10
