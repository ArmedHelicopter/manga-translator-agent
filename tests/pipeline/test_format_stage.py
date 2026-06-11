"""Tests for pipeline format stage."""

from __future__ import annotations

import json

from mga.models import ProjectConfig
from mga.pipeline.format_stage import FormatStage
from mga.pipeline.stages import PipelineContext


def test_format_stage_uses_runtime_payload_pages_when_available(tmp_path) -> None:
    payload = tmp_path / "payload"
    runtime_input = payload / ".runtime-input"
    runtime_input.mkdir(parents=True)
    (runtime_input / "page-0000.png").write_bytes(b"page-0")
    (payload / "pages.json").write_text(
        json.dumps([{"page_index": 0, "artifact": "artifact-0000.json"}]),
        encoding="utf-8",
    )
    missing_input = tmp_path / "missing.pdf"
    ctx = PipelineContext(
        project_config=ProjectConfig(input_format="pdf", source_lang="ja"),
        metadata={
            "input_path": str(missing_input),
            "artifact_payload_dir": str(payload),
        },
    )

    result = FormatStage().execute(ctx)

    assert len(result.pages) == 1
    assert result.pages[0].page_id == "page_0000"
    assert result.pages[0].page_index == 0
    assert result.pages[0].image.path == str(runtime_input / "page-0000.png")
    assert result.artifacts["format"] == {
        "page_count": 1,
        "format": "pdf",
        "source": "artifact_payload",
    }
