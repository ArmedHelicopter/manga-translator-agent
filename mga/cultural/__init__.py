"""Cultural adaptation layer for manga translation.

Single entry point: use get_cultural_service(project_dir) for all operations.
"""

from __future__ import annotations

from pathlib import Path

from .classifier import classify_problem
from .honorific import HonorificCompensator, HonorificLevel
from .strategies import TranslationStrategy, select_strategy

# Lazy exports for heavy modules
__all__ = [
    # Core functions
    "classify_problem",
    "select_strategy",
    # Honorific system
    "HonorificCompensator",
    "HonorificLevel",
    "TranslationStrategy",
    # Service factory (primary interface)
    "get_cultural_service",
    # Lazy exports
    "TerminologyDB",
    "TermState",
    "CulturalAdapter",
    "CoinageDetector",
    "TermGrade",
    "classify_term",
    "classify_batch",
    "load_fictional_script_context",
]


def get_cultural_service(project_dir: Path | str):
    """Get or create singleton CulturalAdapter for project."""
    from .cultural_adapter import CulturalAdapter
    return CulturalAdapter(project_dir)


def __getattr__(name: str):
    if name in ("TermState", "TerminologyDB"):
        from .terminology_db import TerminologyDB, TermState
        return {"TermState": TermState, "TerminologyDB": TerminologyDB}[name]
    if name in ("CulturalAdapter",):
        from .cultural_adapter import CulturalAdapter
        return CulturalAdapter
    if name in ("CoinageDetector",):
        from .coinage_detector import CoinageDetector
        return CoinageDetector
    if name in ("TermGrade", "classify_term", "classify_batch"):
        from .term_classifier import TermGrade, classify_term, classify_batch
        return {"TermGrade": TermGrade, "classify_term": classify_term, "classify_batch": classify_batch}[name]
    if name in ("load_fictional_script_context",):
        from .fictional_scripts import load_fictional_script_context
        return load_fictional_script_context
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")