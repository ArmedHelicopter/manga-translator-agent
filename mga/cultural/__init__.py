"""Cultural adaptation layer for manga translation."""

from .cultural_adapter import CulturalAdapter
from .classifier import CulturalProblemType, classify_problem
from .honorific import HonorificCompensator, HonorificLevel
from .strategies import TranslationStrategy, select_strategy
from .terminology_db import TerminologyDB, TermState

__all__ = [
    "CulturalAdapter",
    "CulturalProblemType",
    "HonorificCompensator",
    "HonorificLevel",
    "TerminologyDB",
    "TermState",
    "TranslationStrategy",
    "classify_problem",
    "select_strategy",
    "CoinageDetector",
    "TermGrade",
    "classify_term",
    "load_fictional_script_context",
]


def __getattr__(name: str):
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
