"""Tests for the OCR guard pipeline stage."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mga.exceptions import RestartPipelineSignal
from mga.models import Bubble, Page, ProjectConfig
from mga.ocr.models import OCRGuardConfig, RecoveryDecision, RecoveryStrategy
from mga.pipeline.ocr_guard_stage import OCRGuardStage
from mga.pipeline.stages import PipelineContext


@pytest.fixture
def make_page():
    def _factory(page_id: str, page_index: int, bubble_texts: list[str]):
        return Page(
            page_id=page_id,
            page_index=page_index,
            bubbles=[
                Bubble(
                    bubble_id=f"{page_id}-b{i}",
                    source_text=text,
                    reading_order=i,
                )
                for i, text in enumerate(bubble_texts)
            ],
        )

    return _factory


@pytest.fixture
def make_pipeline_context(make_page):
    def _factory(
        bubble_texts_by_page: list[list[str]],
        config: OCRGuardConfig | None = None,
    ):
        cfg = config or OCRGuardConfig()
        # ProjectConfig expects dict or None for ocr_guard
        ocr_guard_dict = cfg.model_dump() if cfg else None
        return PipelineContext(
            project_config=ProjectConfig(ocr_guard=ocr_guard_dict),
            pages=[
                make_page(f"p{i:03d}", i, bubble_texts)
                for i, bubble_texts in enumerate(bubble_texts_by_page, start=1)
            ],
        )

    return _factory


def test_stage_disabled_skips_detection(make_pipeline_context):
    context = make_pipeline_context(
        [[], [], []],
        OCRGuardConfig(enabled=False, consecutive_blank_threshold=2),
    )

    result = OCRGuardStage().execute(context)

    assert result.ocr_guard_state["detector_run"] is False
    assert result.ocr_guard_state["enabled"] is False
    assert result.ocr_guard_state["blank_sequence"] is None
    assert result.artifacts["ocr_guard"] == result.ocr_guard_state


def test_stage_enabled_no_blanks_passes(make_pipeline_context):
    context = make_pipeline_context([["read"], ["safe"], ["go!"]])

    result = OCRGuardStage().execute(context)

    assert result.ocr_guard_state["detector_run"] is True
    assert result.ocr_guard_state["blank_sequence"] is None
    assert result.ocr_guard_state["min_text_length"] == 3
    assert "ocr_guard_checkpoint" not in result.metadata
    assert result.artifacts["ocr_guard"] == result.ocr_guard_state


def test_stage_enabled_blanks_below_threshold_passes(make_pipeline_context):
    context = make_pipeline_context(
        [[], [], ["read"]],
        OCRGuardConfig(consecutive_blank_threshold=3),
    )

    result = OCRGuardStage().execute(context)

    assert result.ocr_guard_state["blank_sequence"] is None
    assert result.ocr_guard_state["threshold"] == 3
    assert result.artifacts["ocr_guard"] == result.ocr_guard_state


def test_stage_detects_blanks_and_prompts_recovery(make_pipeline_context, monkeypatch):
    calls = {"prompt": 0, "apply": 0}

    class FakeOrchestrator:
        def __init__(self, config):
            self.config = config

        def prompt_user(self, sequence, context):
            calls["prompt"] += 1
            assert sequence.page_ids == ["p001", "p002", "p003"]
            assert context.metadata["ocr_guard_checkpoint"]["page_count"] == 3
            return RecoveryDecision(strategy=RecoveryStrategy.CONTINUE)

        def apply_strategy(self, decision, context):
            calls["apply"] += 1
            context.ocr_guard_state["recovery_applied"] = decision.model_dump(mode="json")
            return context, False

    monkeypatch.setattr("mga.pipeline.ocr_guard_stage.RecoveryOrchestrator", FakeOrchestrator)
    context = make_pipeline_context([[], [], []], OCRGuardConfig(consecutive_blank_threshold=3))

    result = OCRGuardStage().execute(context)

    assert calls == {"prompt": 1, "apply": 1}
    assert result.metadata["ocr_guard_checkpoint"] == {
        "blank_sequence": {
            "start_index": 1,
            "end_index": 3,
            "page_ids": ["p001", "p002", "p003"],
            "blank_count": 3,
        },
        "page_count": 3,
    }
    assert result.ocr_guard_state["recovery_applied"]["strategy"] == "continue"


def test_stage_raises_restart_signal_on_model_switch(make_pipeline_context, monkeypatch):
    class FakeOrchestrator:
        def __init__(self, config):
            self.config = config

        def prompt_user(self, sequence, context):
            return RecoveryDecision(
                strategy=RecoveryStrategy.SWITCH_OCR_MODEL,
                new_ocr_model="mocr",
            )

        def apply_strategy(self, decision, context):
            context.ocr_guard_state["recovery_applied"] = decision.model_dump(mode="json")
            context.metadata["requested_ocr_model"] = decision.new_ocr_model
            return context, True

    monkeypatch.setattr("mga.pipeline.ocr_guard_stage.RecoveryOrchestrator", FakeOrchestrator)
    context = make_pipeline_context([[], [], []], OCRGuardConfig(consecutive_blank_threshold=3))

    with pytest.raises(RestartPipelineSignal) as exc_info:
        OCRGuardStage().execute(context)

    assert exc_info.value.new_ocr_model == "mocr"
    assert exc_info.value.context_checkpoint is context
    assert context.artifacts["ocr_guard"]["recovery_applied"]["strategy"] == "switch_model"


def test_stage_records_artifacts(make_pipeline_context):
    context = make_pipeline_context(
        [[], [], []],
        OCRGuardConfig(consecutive_blank_threshold=3, auto_recovery_strategy="continue"),
    )

    result = OCRGuardStage().execute(context)

    assert result.artifacts["ocr_guard"] == result.ocr_guard_state
    assert result.artifacts["ocr_guard"]["blank_sequence"] == {
        "start_index": 1,
        "end_index": 3,
        "page_ids": ["p001", "p002", "p003"],
        "blank_count": 3,
    }
    assert result.artifacts["ocr_guard"]["recovery_applied"]["strategy"] == "continue"


def test_resolve_config_from_project_config():
    project_config = SimpleNamespace(
        ocr_guard={
            "enabled": False,
            "consecutive_blank_threshold": 6,
            "min_text_length": 1,
            "auto_recovery_strategy": "CONTINUE",
        }
    )
    context = PipelineContext(project_config=project_config)

    config = OCRGuardStage()._resolve_config(context)

    assert config.enabled is False
    assert config.consecutive_blank_threshold == 6
    assert config.min_text_length == 1
    assert config.auto_recovery_strategy == "continue"
