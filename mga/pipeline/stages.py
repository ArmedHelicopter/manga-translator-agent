"""Base classes for the 7-stage translation pipeline.

Re-exports PipelineContext from context.py for backward compatibility.
New code should import from context.py directly for typed sub-contexts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .context import PipelineContext

# Re-export for backward compatibility
__all__ = ["PipelineContext", "PipelineStage"]


class PipelineStage(ABC):
    """Abstract base class for a single pipeline stage."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Short identifier for this stage."""

    @property
    @abstractmethod
    def order(self) -> int:
        """Execution order (lower runs first)."""

    @abstractmethod
    def execute(self, context: PipelineContext) -> PipelineContext:
        """Run this stage and return the (possibly mutated) context."""