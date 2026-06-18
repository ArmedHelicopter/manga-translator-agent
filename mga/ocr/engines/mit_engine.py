"""MIT OCR model binding for the manga-image-translator runtime.

The 32px/48px/48px_ctc MIT OCR models run inside the external manga-image-translator
runtime subprocess, not inside mga. This engine is a *model-selection marker*: it
registers the model names so the SWITCH_OCR_MODEL recovery strategy can offer them,
and is_available() checks whether the runtime model files exist.

It does NOT perform inference itself — calling extract_text() raises
NotImplementedError with a message pointing to the runtime subprocess.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .base import OCREngine

logger = logging.getLogger(__name__)

# Model name → (ckpt filename, alphabet filename) inside the runtime models dir.
# These match manga-image-translator's model file layout.
_MIT_MODEL_FILES: dict[str, tuple[str, str]] = {
    "48px": ("ocr_ar_48px.ckpt", "alphabet-all-v7.txt"),
    "32px": ("ocr_ar_32px.ckpt", "alphabet-all-v7.txt"),
    "48px_ctc": ("ocr_ar_48px_ctc.ckpt", "alphabet-all-v7.txt"),
}

# Environment variable pointing at the runtime model directory (set by the pipeline
# when invoking the runtime subprocess). Falls back to the bundled external/
# manga-image-translator/models layout.
_MODEL_DIR_ENV = "MANGA_TRANSLATOR_MODEL_DIR"
_DEFAULT_MODEL_SUBDIR = Path("external") / "manga-image-translator" / "models"


class MITOCREngine(OCREngine):
    """MIT OCR model binding for the manga-image-translator runtime.

    Registers the 32px/48px/48px_ctc MIT OCR models for SWITCH_OCR_MODEL recovery.
    Inference happens inside the runtime subprocess — this engine does not extract
    text itself.
    """

    def __init__(self, model_name: str = "48px") -> None:
        if model_name not in _MIT_MODEL_FILES:
            raise ValueError(
                f"Unknown MIT OCR model: {model_name}. "
                f"Choose from {sorted(_MIT_MODEL_FILES)}"
            )
        self._model_name = model_name

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def description(self) -> str:
        return f"MIT {self._model_name} OCR (runtime model)"

    def is_available(self) -> bool:
        """Check whether the runtime model checkpoint exists.

        Returns True if the .ckpt file for this model is present in the runtime
        model directory (env var or bundled external/ path). Never raises.
        """
        ckpt_name, _ = _MIT_MODEL_FILES[self._model_name]
        model_dir = self._resolve_model_dir()
        if model_dir is None:
            return False
        ckpt_path = model_dir / ckpt_name
        available = ckpt_path.is_file()
        logger.debug(
            "MIT OCR %s available=%s (checked %s)",
            self._model_name, available, ckpt_path,
        )
        return available

    def extract_text(self, image_path: str | Path, **kwargs: Any) -> str:
        """MIT OCR inference runs inside the manga-image-translator runtime.

        This engine is a model-selection marker for SWITCH_OCR_MODEL recovery and
        does not perform inference itself. Use the runtime subprocess
        (run_export_artifact / run_render_only) for actual OCR.
        """
        raise NotImplementedError(
            "MIT OCR models run inside the manga-image-translator runtime subprocess. "
            "Use run_export_artifact() or run_render_only() for inference; "
            "this engine is a model-selection marker for SWITCH_OCR_MODEL recovery."
        )

    @staticmethod
    def supported_models() -> list[str]:
        """Return the list of supported MIT OCR model names."""
        return sorted(_MIT_MODEL_FILES)

    @classmethod
    def _resolve_model_dir(cls) -> Path | None:
        """Resolve the runtime model directory from env var or bundled path."""
        env_dir = os.environ.get(_MODEL_DIR_ENV)
        if env_dir:
            return Path(env_dir)
        # Fall back to the project-relative bundled path if it exists.
        # This is a best-effort check; the runtime sets the env var when it runs.
        project_root = Path(__file__).resolve()
        # mga/ocr/engines/mit_engine.py → project root is 4 levels up.
        for parent in project_root.parents:
            candidate = parent / _DEFAULT_MODEL_SUBDIR
            if candidate.is_dir():
                return candidate
        return None
