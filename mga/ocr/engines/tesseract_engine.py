"""Tesseract OCR engine wrapper."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .base import OCREngine

logger = logging.getLogger(__name__)


class TesseractEngine(OCREngine):
    """OCR engine using Tesseract via pytesseract.

    Tesseract is an open-source OCR engine that supports 100+ languages.
    This wrapper uses the pytesseract Python binding for integration.

    Requirements:
        - Tesseract binary installed on the system
        - pytesseract Python package installed

    Install:
        - Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
        - Linux: sudo apt install tesseract-ocr
        - macOS: brew install tesseract
        - Python: pip install pytesseract
    """

    def __init__(
        self,
        *,
        lang: str = "jpn",
        config: str = "",
        tesseract_cmd: str | None = None,
    ) -> None:
        """Initialize Tesseract engine.

        Args:
            lang: Tesseract language code (default: "jpn" for Japanese)
            config: Additional Tesseract configuration string
            tesseract_cmd: Override path to tesseract binary
        """
        self._lang = lang
        self._config = config
        self._tesseract_cmd = tesseract_cmd
        self._pytesseract = None

    @property
    def name(self) -> str:
        return "tesseract"

    @property
    def description(self) -> str:
        return "Tesseract OCR engine (open-source, multi-language)"

    def is_available(self) -> bool:
        """Check if pytesseract and Tesseract binary are available."""
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True
        except (ImportError, EnvironmentError, OSError):
            return False

    def extract_text(self, image_path: str | Path, **kwargs: Any) -> str:
        """Extract text from an image using Tesseract.

        Args:
            image_path: Path to the image file
            **kwargs: Override parameters (lang, config)

        Returns:
            Extracted text as a string

        Raises:
            ImportError: If pytesseract is not installed
            EnvironmentError: If Tesseract binary is not found
        """
        import pytesseract
        from PIL import Image

        if self._tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd

        lang = kwargs.get("lang", self._lang)
        config = kwargs.get("config", self._config)

        image = Image.open(str(image_path))
        text = pytesseract.image_to_string(image, lang=lang, config=config)

        logger.debug(
            "Tesseract extracted %d chars from %s (lang=%s)",
            len(text), image_path, lang,
        )
        return text.strip()

    def extract_data(self, image_path: str | Path, **kwargs: Any) -> list[dict[str, Any]]:
        """Extract structured OCR data with bounding boxes.

        Args:
            image_path: Path to the image file
            **kwargs: Override parameters (lang, config)

        Returns:
            List of dicts with 'text', 'bbox', 'confidence' keys
        """
        import pytesseract
        from PIL import Image

        if self._tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = self._tesseract_cmd

        lang = kwargs.get("lang", self._lang)
        config = kwargs.get("config", self._config)

        image = Image.open(str(image_path))
        data = pytesseract.image_to_data(image, lang=lang, config=config, output_type=pytesseract.Output.DICT)

        results = []
        n = len(data.get("text", []))
        for i in range(n):
            text = data["text"][i].strip()
            if not text:
                continue
            results.append({
                "text": text,
                "bbox": {
                    "x": data["left"][i],
                    "y": data["top"][i],
                    "width": data["width"][i],
                    "height": data["height"][i],
                },
                "confidence": data["conf"][i],
            })

        logger.debug(
            "Tesseract extracted %d regions from %s",
            len(results), image_path,
        )
        return results
