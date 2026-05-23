"""Abstract base class for format adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Iterator

from ..models.format import PageRef, TranslatedPage


class FormatAdapter(ABC):
    """Base class for input format adapters.

    Each adapter knows how to extract PageRef objects from a specific
    input format and how to repack translated pages back to output.
    """

    @abstractmethod
    def extract(self, input_path: Path) -> Iterator[PageRef]:
        """Extract page references from the input path."""

    @abstractmethod
    def repack(self, pages: Iterator[TranslatedPage], output_path: Path) -> None:
        """Repack translated pages to the output path."""
