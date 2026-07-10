"""Compatibility shim for mga.models."""

from mga.models import *  # noqa: F401,F403
from mga.models import (  # explicit re-exports for clarity
    BoundingBox,
    Bubble,
    Page,
    PageImage,
    TranslationCandidate,
    Utterance,
    ProjectConfig,
    ProviderRoute,
    StageProviderConfig,
    PageRef,
    TranslatedPage,
)

__all__ = [
    "BoundingBox",
    "Bubble",
    "Page",
    "PageImage",
    "TranslationCandidate",
    "Utterance",
    "ProjectConfig",
    "ProviderRoute",
    "StageProviderConfig",
    "PageRef",
    "TranslatedPage",
]
