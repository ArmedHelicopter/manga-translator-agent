"""OCR engine bindings for text extraction.

Provides a unified interface for different OCR backends:
- TesseractEngine: Python wrapper for Tesseract OCR
- MOCREngine: Framework for manga-optimized OCR models

Engines are registered with OCREngineRegistry and selected by name,
enabling the SWITCH_OCR_MODEL recovery strategy.
"""

from __future__ import annotations

from .base import OCREngine, OCREngineRegistry
from .tesseract_engine import TesseractEngine

__all__ = [
    "OCREngine",
    "OCREngineRegistry",
    "TesseractEngine",
]


def __getattr__(name: str):
    """Lazy-load MOCREngine only when requested."""
    if name == "MOCREngine":
        from .mocr_engine import MOCREngine
        return MOCREngine
    raise AttributeError(name)
