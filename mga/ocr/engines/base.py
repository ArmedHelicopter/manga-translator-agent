"""Base class and registry for OCR engines."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class OCREngine(ABC):
    """Abstract base class for OCR engines.

    Each engine wraps a specific OCR backend and provides a unified
    interface for text extraction from images.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Engine identifier used in config and recovery strategies."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description of the engine."""
        ...

    @abstractmethod
    def extract_text(self, image_path: str | Path, **kwargs: Any) -> str:
        """Extract text from an image file.

        Args:
            image_path: Path to the image file
            **kwargs: Engine-specific parameters

        Returns:
            Extracted text as a single string
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the engine's backend is installed and available.

        Returns:
            True if the engine can be used, False otherwise
        """
        ...


class OCREngineRegistry:
    """Registry for OCR engines, enabling SWITCH_OCR_MODEL recovery.

    Engines are registered by name and can be selected at runtime.
    The registry is used by RecoveryOrchestrator to apply the
    SWITCH_OCR_MODEL strategy.
    """

    def __init__(self) -> None:
        self._engines: dict[str, OCREngine] = {}

    def register(self, engine: OCREngine) -> None:
        """Register an OCR engine.

        Args:
            engine: OCREngine instance to register
        """
        self._engines[engine.name] = engine
        logger.debug("Registered OCR engine: %s", engine.name)

    def get(self, name: str) -> OCREngine | None:
        """Get an engine by name.

        Args:
            name: Engine identifier

        Returns:
            OCREngine instance, or None if not registered
        """
        return self._engines.get(name)

    def list_engines(self) -> list[dict[str, str]]:
        """List all registered engines with their info.

        Returns:
            List of dicts with 'name' and 'description' keys
        """
        return [
            {"name": engine.name, "description": engine.description}
            for engine in self._engines.values()
        ]

    def list_available(self) -> list[dict[str, str]]:
        """List only engines whose backends are available.

        Returns:
            List of dicts with 'name' and 'description' keys
        """
        return [
            {"name": engine.name, "description": engine.description}
            for engine in self._engines.values()
            if engine.is_available()
        ]

    @classmethod
    def default(cls) -> "OCREngineRegistry":
        """Create a registry with all built-in engines registered.

        Returns:
            Registry with TesseractEngine and MOCREngine registered
        """
        registry = cls()

        from .tesseract_engine import TesseractEngine
        registry.register(TesseractEngine())

        # Lazy-register MOCR only if available
        try:
            from .mocr_engine import MOCREngine
            registry.register(MOCREngine())
        except ImportError:
            logger.debug("MOCR engine not available")

        return registry
