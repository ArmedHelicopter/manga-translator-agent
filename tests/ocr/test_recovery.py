"""Tests for OCR recovery orchestration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from mga.exceptions import StageExecutionError
from mga.models import ProjectConfig, ProviderRoute, StageProviderConfig
from mga.ocr.models import BlankPageSequence, OCRGuardConfig, RecoveryDecision, RecoveryStrategy
from mga.ocr.recovery import RecoveryOrchestrator
from mga.pipeline.stages import PipelineContext


class InteractiveStdin:
    def isatty(self):
        return True


class NonInteractiveStdin:
    def isatty(self):
        return False


@pytest.fixture
def blank_sequence():
    return BlankPageSequence(
        start_index=5,
        end_index=7,
        page_ids=["p005", "p006", "p007"],
        blank_count=3,
    )


@pytest.fixture
def mock_context(blank_sequence):
    return PipelineContext(
        project_config=ProjectConfig(
            provider_routes={
                "vision": StageProviderConfig(
                    primary=ProviderRoute(provider="openai", model="gpt-4o-mini")
                )
            }
        ),
        metadata={
            "ocr_model": "48px",
            "available_ocr_models": ["48px", "mocr"],
        },
        ocr_guard_state={"blank_sequence": blank_sequence.model_dump(mode="json")},
    )


def test_auto_decision_none_returns_none(blank_sequence):
    orchestrator = RecoveryOrchestrator(OCRGuardConfig(auto_recovery_strategy=None))

    assert orchestrator._auto_decision(blank_sequence) is None


def test_auto_decision_skip_is_invalid(blank_sequence):
    config = OCRGuardConfig.model_construct(
        auto_recovery_strategy="skip",
        consecutive_blank_threshold=3,
        min_text_length=3,
        hybrid_vision_model_override=None,
    )
    orchestrator = RecoveryOrchestrator(config)

    with pytest.raises(StageExecutionError):
        orchestrator._auto_decision(blank_sequence)


def test_auto_decision_continue(blank_sequence, mock_context):
    orchestrator = RecoveryOrchestrator(OCRGuardConfig(auto_recovery_strategy="continue"))

    decision = orchestrator.prompt_user(blank_sequence, mock_context)

    assert decision.strategy == RecoveryStrategy.CONTINUE


def test_auto_decision_abort(blank_sequence, mock_context):
    orchestrator = RecoveryOrchestrator(OCRGuardConfig(auto_recovery_strategy="abort"))

    decision = orchestrator.prompt_user(blank_sequence, mock_context)

    assert decision.strategy == RecoveryStrategy.ABORT


def test_auto_decision_adjust_threshold(blank_sequence, mock_context):
    orchestrator = RecoveryOrchestrator(
        OCRGuardConfig(auto_recovery_strategy="adjust_threshold", consecutive_blank_threshold=3)
    )

    decision = orchestrator.prompt_user(blank_sequence, mock_context)

    assert decision.strategy == RecoveryStrategy.ADJUST_THRESHOLD
    assert decision.new_threshold == 4


def test_auto_decision_hybrid(blank_sequence, mock_context):
    orchestrator = RecoveryOrchestrator(
        OCRGuardConfig(auto_recovery_strategy="hybrid", hybrid_vision_model_override="vision-override")
    )

    decision = orchestrator.prompt_user(blank_sequence, mock_context)

    assert decision.strategy == RecoveryStrategy.HYBRID_MODE
    assert decision.hybrid_mode_config == {
        "enabled": True,
        "vision_model_override": "vision-override",
    }


def test_auto_decision_invalid_raises(blank_sequence):
    config = OCRGuardConfig.model_construct(
        auto_recovery_strategy="bogus",
        consecutive_blank_threshold=3,
        min_text_length=3,
        hybrid_vision_model_override=None,
    )
    orchestrator = RecoveryOrchestrator(config)

    with pytest.raises(StageExecutionError):
        orchestrator._auto_decision(blank_sequence)


def test_prompt_user_interactive_continue(blank_sequence, mock_context, monkeypatch):
    orchestrator = RecoveryOrchestrator(OCRGuardConfig())
    monkeypatch.setattr("sys.stdin", InteractiveStdin())
    monkeypatch.setattr("builtins.input", lambda _prompt: "4")

    decision = orchestrator.prompt_user(blank_sequence, mock_context)

    assert decision.strategy == RecoveryStrategy.CONTINUE


def test_prompt_user_interactive_adjust_threshold(blank_sequence, mock_context, monkeypatch):
    inputs = iter(["2", "6"])
    orchestrator = RecoveryOrchestrator(OCRGuardConfig())
    monkeypatch.setattr("sys.stdin", InteractiveStdin())
    monkeypatch.setattr("builtins.input", lambda _prompt: next(inputs))

    decision = orchestrator.prompt_user(blank_sequence, mock_context)

    assert decision.strategy == RecoveryStrategy.ADJUST_THRESHOLD
    assert decision.new_threshold == 6


def test_apply_switch_ocr_model_sets_metadata_and_restarts(mock_context):
    orchestrator = RecoveryOrchestrator(OCRGuardConfig())
    decision = RecoveryDecision(
        strategy=RecoveryStrategy.SWITCH_OCR_MODEL,
        new_ocr_model="mocr",
    )

    context, should_restart = orchestrator.apply_strategy(decision, mock_context)

    assert context is mock_context
    assert should_restart is True
    assert context.metadata["requested_ocr_model"] == "mocr"
    assert context.ocr_guard_state["recovery_applied"]["strategy"] == "switch_model"


def test_apply_adjust_threshold_updates_state(mock_context):
    orchestrator = RecoveryOrchestrator(OCRGuardConfig())
    decision = RecoveryDecision(
        strategy=RecoveryStrategy.ADJUST_THRESHOLD,
        new_threshold=8,
    )

    context, should_restart = orchestrator.apply_strategy(decision, mock_context)

    assert should_restart is False
    assert context.ocr_guard_state["threshold"] == 8
    assert context.ocr_guard_state["recovery_applied"]["new_threshold"] == 8


def test_apply_hybrid_mode_populates_hybrid_pages(mock_context):
    mock_context.ocr_guard_state["hybrid_mode_pages"] = ["p001", "p006"]
    orchestrator = RecoveryOrchestrator(OCRGuardConfig())
    decision = RecoveryDecision(
        strategy=RecoveryStrategy.HYBRID_MODE,
        hybrid_mode_config={"enabled": True, "vision_model_override": "vision-override"},
    )

    context, should_restart = orchestrator.apply_strategy(decision, mock_context)

    assert should_restart is False
    assert context.ocr_guard_state["hybrid_mode_pages"] == ["p001", "p005", "p006", "p007"]
    assert context.ocr_guard_state["hybrid_mode_config"] == {
        "enabled": True,
        "vision_model_override": "vision-override",
    }


def test_apply_continue_records_decision(mock_context):
    orchestrator = RecoveryOrchestrator(OCRGuardConfig())
    decision = RecoveryDecision(strategy=RecoveryStrategy.CONTINUE)

    context, should_restart = orchestrator.apply_strategy(decision, mock_context)

    assert should_restart is False
    assert context.ocr_guard_state["recovery_applied"]["strategy"] == "continue"


def test_apply_abort_raises_stage_error(mock_context):
    orchestrator = RecoveryOrchestrator(OCRGuardConfig())
    decision = RecoveryDecision(strategy=RecoveryStrategy.ABORT)

    with pytest.raises(StageExecutionError):
        orchestrator.apply_strategy(decision, mock_context)

    assert mock_context.ocr_guard_state["recovery_applied"]["strategy"] == "abort"


def test_prompt_user_non_interactive_no_auto_raises(blank_sequence, mock_context, monkeypatch):
    orchestrator = RecoveryOrchestrator(OCRGuardConfig())
    monkeypatch.setattr("sys.stdin", NonInteractiveStdin())

    with pytest.raises(StageExecutionError):
        orchestrator.prompt_user(blank_sequence, mock_context)


def test_available_ocr_models_from_context(mock_context):
    orchestrator = RecoveryOrchestrator(OCRGuardConfig())

    assert orchestrator._available_ocr_models(mock_context) == [
        {"name": "48px", "description": "Configured OCR model"},
        {"name": "mocr", "description": "Configured OCR model"},
    ]


def test_available_ocr_models_defaults():
    context = SimpleNamespace(metadata={})
    orchestrator = RecoveryOrchestrator(OCRGuardConfig())

    models = orchestrator._available_ocr_models(context)

    assert [model["name"] for model in models] == ["48px", "32px", "48px_ctc", "mocr"]
