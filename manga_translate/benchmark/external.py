"""Compatibility shim for mga.benchmark.external."""

from mga.benchmark.external import *  # noqa: F401,F403
from mga.benchmark.external import (  # explicit re-exports
    resolve_manga_image_translator_repo,
    run_manga_image_translator_baseline,
)

__all__ = [
    "resolve_manga_image_translator_repo",
    "run_manga_image_translator_baseline",
]
