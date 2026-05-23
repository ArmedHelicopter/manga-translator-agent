"""Compatibility shim for mga.artifacts."""

from mga.artifacts import *  # noqa: F401,F403
from mga.artifacts import ArtifactStore

__all__ = ["ArtifactStore"]
