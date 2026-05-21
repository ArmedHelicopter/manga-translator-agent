"""Compatibility shim for mga.benchmark.evaluate."""

from mga.benchmark.evaluate import *  # noqa: F401,F403
from mga.benchmark.evaluate import (  # explicit re-exports
    OcrResult,
    _run_ocr_spec,
    _run_tesseract_ocr,
    run_extraction_benchmark,
    run_external_translation_benchmark,
    run_translation_benchmark,
    select_sample_pages,
)

__all__ = [
    "OcrResult",
    "_run_ocr_spec",
    "_run_tesseract_ocr",
    "run_extraction_benchmark",
    "run_external_translation_benchmark",
    "run_translation_benchmark",
    "select_sample_pages",
]
