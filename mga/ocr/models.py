"""Data models for OCR blank-page detection and recovery."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class RecoveryStrategy(str, Enum):
    """User recovery options when blank pages are detected."""

    SWITCH_OCR_MODEL = "switch_model"
    ADJUST_THRESHOLD = "adjust_threshold"
    HYBRID_MODE = "hybrid"
    CONTINUE = "continue"
    ABORT = "abort"


class OCRGuardConfig(BaseModel):
    """Configuration for OCR blank-page detection."""

    enabled: bool = True
    consecutive_blank_threshold: int = Field(default=3, ge=1)
    min_text_length: int = Field(default=3, ge=0)
    auto_recovery_strategy: str | None = None
    hybrid_mode_enabled: bool = False
    hybrid_vision_model_override: str | None = None

    @field_validator("auto_recovery_strategy", mode="after")
    @classmethod
    def validate_strategy(cls, v: str | None) -> str | None:
        """Validate auto_recovery_strategy against RecoveryStrategy enum."""
        if v is None:
            return v

        normalized = v.strip().lower()
        if normalized in {"none", "null", "prompt", ""}:
            return None

        valid_values = {s.value for s in RecoveryStrategy}
        if normalized not in valid_values:
            raise ValueError(
                f"auto_recovery_strategy must be one of {valid_values} or null, got: {v}"
            )

        return normalized


class BlankPageSequence(BaseModel):
    """Detected consecutive blank page range."""

    start_index: int
    end_index: int
    page_ids: list[str]
    blank_count: int


class RecoveryDecision(BaseModel):
    """User's recovery choice and parameters."""

    strategy: RecoveryStrategy
    new_threshold: int | None = None
    new_ocr_model: str | None = None
    hybrid_mode_config: dict[str, Any] | None = None
