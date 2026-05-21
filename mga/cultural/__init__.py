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
]
