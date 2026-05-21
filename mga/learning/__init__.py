"""Translation learning engine — extract character profiles, terminology, and style from existing translations."""

from .models import AlignedPageData, LearningResult, PagePair
from .aligner import align, align_from_flat_dirs
from .engine import LearningEngine
from .validator import validate

__all__ = [
    "AlignedPageData",
    "LearningResult",
    "LearningEngine",
    "PagePair",
    "align",
    "align_from_flat_dirs",
    "validate",
]
