"""Tests for OCR guard data models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mga.ocr.models import BlankPageSequence, OCRGuardConfig, RecoveryDecision, RecoveryStrategy


def test_recovery_strategy_enum_values():
    assert {strategy.value for strategy in RecoveryStrategy} == {
        "switch_model",
        "adjust_threshold",
        "hybrid",
        "continue",
        "abort",
    }


def test_ocr_guard_config_defaults():
    config = OCRGuardConfig()

    assert config.enabled is True
    assert config.consecutive_blank_threshold == 3
    assert config.min_text_length == 3
    assert config.auto_recovery_strategy is None
    assert config.hybrid_mode_enabled is False
    assert config.hybrid_vision_model_override is None


def test_ocr_guard_config_normalizes_auto_recovery_strategy():
    assert OCRGuardConfig(auto_recovery_strategy=" CONTINUE ").auto_recovery_strategy == "continue"
    assert OCRGuardConfig(auto_recovery_strategy="prompt").auto_recovery_strategy is None
    assert OCRGuardConfig(auto_recovery_strategy="none").auto_recovery_strategy is None
    assert OCRGuardConfig(auto_recovery_strategy="null").auto_recovery_strategy is None
    assert OCRGuardConfig(auto_recovery_strategy="").auto_recovery_strategy is None


def test_ocr_guard_config_validation_rejects_invalid_strategy():
    with pytest.raises(ValidationError):
        OCRGuardConfig(auto_recovery_strategy="skip")


def test_ocr_guard_config_validation_min_threshold():
    with pytest.raises(ValidationError):
        OCRGuardConfig(consecutive_blank_threshold=0)


def test_ocr_guard_config_validation_min_text_length():
    with pytest.raises(ValidationError):
        OCRGuardConfig(min_text_length=-1)


def test_blank_page_sequence_from_dict():
    sequence = BlankPageSequence.model_validate({
        "start_index": 5,
        "end_index": 7,
        "page_ids": ["p005", "p006", "p007"],
        "blank_count": 3,
    })

    assert sequence.start_index == 5
    assert sequence.end_index == 7
    assert sequence.page_ids == ["p005", "p006", "p007"]
    assert sequence.blank_count == 3
    assert sequence.model_dump(mode="json") == {
        "start_index": 5,
        "end_index": 7,
        "page_ids": ["p005", "p006", "p007"],
        "blank_count": 3,
    }


def test_recovery_decision_minimal():
    decision = RecoveryDecision(strategy=RecoveryStrategy.CONTINUE)

    assert decision.strategy == RecoveryStrategy.CONTINUE
    assert decision.new_threshold is None
    assert decision.new_ocr_model is None
    assert decision.hybrid_mode_config is None
    assert decision.model_dump(mode="json") == {
        "strategy": "continue",
        "new_threshold": None,
        "new_ocr_model": None,
        "hybrid_mode_config": None,
    }


def test_recovery_decision_with_threshold():
    decision = RecoveryDecision(
        strategy=RecoveryStrategy.ADJUST_THRESHOLD,
        new_threshold=6,
    )

    assert decision.new_threshold == 6
    assert decision.model_dump(mode="json")["strategy"] == "adjust_threshold"


def test_recovery_decision_with_ocr_model():
    decision = RecoveryDecision(
        strategy=RecoveryStrategy.SWITCH_OCR_MODEL,
        new_ocr_model="mocr",
    )

    assert decision.new_ocr_model == "mocr"
    assert decision.model_dump(mode="json")["strategy"] == "switch_model"
