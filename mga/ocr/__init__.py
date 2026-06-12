"""OCR guard utilities for detecting blank OCR output and recovery choices."""

from __future__ import annotations

from .models import (
    BlankPageSequence,
    OCRGuardConfig,
    RecoveryDecision,
    RecoveryStrategy,
)

__all__ = [
    "BlankPageDetector",
    "BlankPageSequence",
    "OCRGuardConfig",
    "RecoveryDecision",
    "RecoveryOrchestrator",
    "RecoveryStrategy",
]


def __getattr__(name: str):
    """Lazily expose detector/recovery classes without creating import cycles."""
    if name == "BlankPageDetector":
        from .detector import BlankPageDetector

        return BlankPageDetector
    if name == "RecoveryOrchestrator":
        from .recovery import RecoveryOrchestrator

        return RecoveryOrchestrator
    raise AttributeError(name)
