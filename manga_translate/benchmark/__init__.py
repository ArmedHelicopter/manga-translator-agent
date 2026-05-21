"""Compatibility shim for mga.benchmark."""

from mga.benchmark import *  # noqa: F401,F403
from mga.benchmark import run_external_translation_benchmark, run_manga_image_translator_baseline

__all__ = [
    "run_external_translation_benchmark",
    "run_manga_image_translator_baseline",
]
