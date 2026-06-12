"""MOCR (Manga OCR) engine framework.

MOCR models are specialized for manga text recognition and typically
outperform general-purpose OCR on manga-specific challenges like
vertical text, furigana, and stylized fonts.

This module provides the engine framework. Actual model inference
requires a compatible MOCR model to be installed or accessible.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base import OCREngine

logger = logging.getLogger(__name__)


class MOCREngine(OCREngine):
    """OCR engine using manga-optimized OCR models.

    MOCR models are specialized for manga text recognition:
    - Vertical and horizontal text
    - Furigana annotation handling
    - Stylized fonts and hand-drawn text
    - Speech bubble boundary detection

    Requirements:
        - A compatible MOCR model (e.g., manga-ocr from Hugging Face)
        - torch and transformers packages

    Install:
        pip install manga-ocr transformers torch
    """

    def __init__(
        self,
        *,
        model_name: str = "kha-white/manga-ocr-base",
        device: str | None = None,
    ) -> None:
        """Initialize MOCR engine.

        Args:
            model_name: Hugging Face model identifier
            device: Device for inference ('cpu', 'cuda', etc.)
        """
        self._model_name = model_name
        self._device = device
        self._model = None

    @property
    def name(self) -> str:
        return "mocr"

    @property
    def description(self) -> str:
        return f"Manga OCR model ({self._model_name})"

    def is_available(self) -> bool:
        """Check if MOCR model dependencies are available."""
        try:
            import torch  # noqa: F401
            from manga_ocr import MangaOcr  # noqa: F401
            return True
        except ImportError:
            return False

    def _load_model(self) -> Any:
        """Lazy-load the MOCR model."""
        if self._model is not None:
            return self._model

        from manga_ocr import MangaOcr

        logger.info("Loading MOCR model: %s", self._model_name)
        self._model = MangaOcr(pretrained_model_name_or_path=self._model_name)
        return self._model

    def extract_text(self, image_path: str | Path, **kwargs: Any) -> str:
        """Extract text from a manga image using MOCR.

        Args:
            image_path: Path to the image file
            **kwargs: Override parameters

        Returns:
            Extracted text as a string

        Raises:
            ImportError: If manga_ocr is not installed
        """
        from PIL import Image

        model = self._load_model()
        image = Image.open(str(image_path))
        text = model(image)

        logger.debug(
            "MOCR extracted %d chars from %s",
            len(text), image_path,
        )
        return text.strip()
