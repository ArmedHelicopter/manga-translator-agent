"""Integration tests for OCR guard wiring into vision stage."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from mga.core.models import PipelineContext
from mga.exceptions import RestartPipelineSignal, StageExecutionError
from mga.models import Page, PageImage, ProjectConfig
from mga.ocr import OCRGuardConfig, RecoveryStrategy
from mga.pipeline.vision_stage import OCRArtifactStage


@pytest.fixture
def temp_artifact_dir(tmp_path: Path) -> Path:
    """Create a temporary artifact directory with pages.json and per-page artifacts."""
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    pages_manifest = [
        {"page_index": 0, "artifact": "page_0000.json"},
        {"page_index": 1, "artifact": "page_0001.json"},
        {"page_index": 2, "artifact": "page_0002.json"},
    ]
    (artifact_dir / "pages.json").write_text(json.dumps(pages_manifest), encoding="utf-8")
    return artifact_dir


def create_page_artifact(artifact_dir: Path, page_index: int, regions: list[dict]) -> None:
    """Write a single page artifact JSON file."""
    artifact_file = artifact_dir / f"page_{page_index:04d}.json"
    artifact_file.write_text(
        json.dumps({"text_regions": regions}),
        encoding="utf-8",
    )


def test_blank_sequence_triggers_recovery_prompt(temp_artifact_dir: Path):
    """Test that 3 consecutive blank pages trigger the recovery prompt."""
    # Create 3 blank pages
    for i in range(3):
        create_page_artifact(temp_artifact_dir, i, [])

    context = PipelineContext(
        project_config=ProjectConfig(
            ocr_guard={"enabled": True, "consecutive_blank_threshold": 3}
        ),
        pages=[
            Page(page_id=f"page-{i:04d}", page_index=i, image=PageImage(path=f"page_{i}.jpg"))
            for i in range(3)
        ],
        metadata={"artifact_payload_dir": str(temp_artifact_dir)},
    )

    stage = OCRArtifactStage()

    # Mock the prompt_user to return CONTINUE
    with patch("mga.pipeline.vision_stage.RecoveryOrchestrator.prompt_user") as mock_prompt:
        from mga.ocr import RecoveryDecision
        mock_prompt.return_value = RecoveryDecision(strategy=RecoveryStrategy.CONTINUE)
        result_context = stage.execute(context)

    # Verify prompt was called
    mock_prompt.assert_called_once()
    sequence_arg = mock_prompt.call_args[0][0]
    assert sequence_arg.blank_count == 3
    assert sequence_arg.start_index == 0
    assert sequence_arg.end_index == 2

    # Verify state recorded
    assert "blank_sequence" in result_context.ocr_guard_state
    assert result_context.ocr_guard_state["blank_sequence"]["blank_count"] == 3


def test_auto_recovery_applies_continue_strategy(temp_artifact_dir: Path):
    """Test that auto_recovery_strategy=continue bypasses prompt and continues."""
    for i in range(3):
        create_page_artifact(temp_artifact_dir, i, [])

    context = PipelineContext(
        project_config=ProjectConfig(
            ocr_guard={
                "enabled": True,
                "consecutive_blank_threshold": 3,
                "auto_recovery_strategy": "continue",
            }
        ),
        pages=[
            Page(page_id=f"page-{i:04d}", page_index=i, image=PageImage(path=f"page_{i}.jpg"))
            for i in range(3)
        ],
        metadata={"artifact_payload_dir": str(temp_artifact_dir)},
    )

    stage = OCRArtifactStage()
    result_context = stage.execute(context)

    # Verify auto strategy applied without prompting
    assert result_context.ocr_guard_state["recovery_applied"]["strategy"] == "continue"


def test_abort_strategy_raises_stage_error(temp_artifact_dir: Path):
    """Test that ABORT strategy raises StageExecutionError."""
    for i in range(3):
        create_page_artifact(temp_artifact_dir, i, [])

    context = PipelineContext(
        project_config=ProjectConfig(
            ocr_guard={
                "enabled": True,
                "consecutive_blank_threshold": 3,
                "auto_recovery_strategy": "abort",
            }
        ),
        pages=[
            Page(page_id=f"page-{i:04d}", page_index=i, image=PageImage(path=f"page_{i}.jpg"))
            for i in range(3)
        ],
        metadata={"artifact_payload_dir": str(temp_artifact_dir)},
    )

    stage = OCRArtifactStage()

    with pytest.raises(StageExecutionError, match="User aborted pipeline"):
        stage.execute(context)


def test_switch_model_raises_restart_signal(temp_artifact_dir: Path):
    """Test that SWITCH_OCR_MODEL strategy raises RestartPipelineSignal."""
    for i in range(3):
        create_page_artifact(temp_artifact_dir, i, [])

    context = PipelineContext(
        project_config=ProjectConfig(
            ocr_guard={"enabled": True, "consecutive_blank_threshold": 3}
        ),
        pages=[
            Page(page_id=f"page-{i:04d}", page_index=i, image=PageImage(path=f"page_{i}.jpg"))
            for i in range(3)
        ],
        metadata={"artifact_payload_dir": str(temp_artifact_dir)},
    )

    stage = OCRArtifactStage()

    with patch("mga.pipeline.vision_stage.RecoveryOrchestrator.prompt_user") as mock_prompt:
        from mga.ocr import RecoveryDecision
        mock_prompt.return_value = RecoveryDecision(
            strategy=RecoveryStrategy.SWITCH_OCR_MODEL,
            new_ocr_model="mocr",
        )
        with pytest.raises(RestartPipelineSignal) as exc_info:
            stage.execute(context)

    assert exc_info.value.new_ocr_model == "mocr"


def test_no_detection_when_threshold_not_met(temp_artifact_dir: Path):
    """Test that 2 blank pages don't trigger detection (threshold=3)."""
    create_page_artifact(temp_artifact_dir, 0, [])
    create_page_artifact(temp_artifact_dir, 1, [])
    create_page_artifact(temp_artifact_dir, 2, [{"text": "some text", "lines": [[0, 0, 100, 100]]}])

    context = PipelineContext(
        project_config=ProjectConfig(
            ocr_guard={"enabled": True, "consecutive_blank_threshold": 3}
        ),
        pages=[
            Page(page_id=f"page-{i:04d}", page_index=i, image=PageImage(path=f"page_{i}.jpg"))
            for i in range(3)
        ],
        metadata={"artifact_payload_dir": str(temp_artifact_dir)},
    )

    stage = OCRArtifactStage()
    result_context = stage.execute(context)

    # No detection should occur
    assert "blank_sequence" not in result_context.ocr_guard_state


def test_ocr_guard_disabled_skips_check(temp_artifact_dir: Path):
    """Test that disabled OCR guard skips all checks."""
    for i in range(3):
        create_page_artifact(temp_artifact_dir, i, [])

    context = PipelineContext(
        project_config=ProjectConfig(
            ocr_guard={"enabled": False, "consecutive_blank_threshold": 3}
        ),
        pages=[
            Page(page_id=f"page-{i:04d}", page_index=i, image=PageImage(path=f"page_{i}.jpg"))
            for i in range(3)
        ],
        metadata={"artifact_payload_dir": str(temp_artifact_dir)},
    )

    stage = OCRArtifactStage()
    result_context = stage.execute(context)

    # Should complete without detection
    assert "blank_sequence" not in result_context.ocr_guard_state
