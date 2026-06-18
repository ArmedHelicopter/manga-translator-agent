"""Tests for MIT OCR engine bindings."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mga.ocr.engines.base import OCREngineRegistry
from mga.ocr.engines.mit_engine import MITOCREngine, _MIT_MODEL_FILES


class TestMITOCREngine:
    """Tests for MITOCREngine model-selection marker."""

    def test_supported_models(self):
        """supported_models returns 32px, 48px, 48px_ctc."""
        models = MITOCREngine.supported_models()
        assert "48px" in models
        assert "32px" in models
        assert "48px_ctc" in models
        assert len(models) == 3

    def test_name_and_description(self):
        """Each model variant reports correct name/description."""
        for model_name in MITOCREngine.supported_models():
            engine = MITOCREngine(model_name)
            assert engine.name == model_name
            assert "MIT" in engine.description
            assert model_name in engine.description

    def test_invalid_model_raises(self):
        """Unknown model name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown MIT OCR model"):
            MITOCREngine("99px")

    def test_extract_text_raises_not_implemented(self, tmp_path: Path):
        """extract_text raises NotImplementedError (runtime does inference)."""
        engine = MITOCREngine("48px")
        dummy_image = tmp_path / "page.png"
        dummy_image.write_bytes(b"\x89PNG\r\n")

        with pytest.raises(NotImplementedError, match="runtime subprocess"):
            engine.extract_text(dummy_image)

    def test_is_available_returns_bool(self):
        """is_available returns a bool and never raises."""
        engine = MITOCREngine("48px")
        # The actual value depends on whether model files exist; we only
        # assert it doesn't raise and returns a bool.
        result = engine.is_available()
        assert isinstance(result, bool)

    def test_is_available_false_when_model_dir_missing(self):
        """is_available returns False when no model dir is resolvable."""
        engine = MITOCREngine("48px")
        with patch.dict("os.environ", {}, clear=True):
            # Force _resolve_model_dir to return None by patching it
            with patch.object(MITOCREngine, "_resolve_model_dir", return_value=None):
                assert engine.is_available() is False

    def test_is_available_true_when_ckpt_exists(self, tmp_path: Path):
        """is_available returns True when the .ckpt file exists."""
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        (model_dir / "ocr_ar_48px.ckpt").write_bytes(b"fake")
        (model_dir / "alphabet-all-v7.txt").write_text("a", encoding="utf-8")

        engine = MITOCREngine("48px")
        with patch.dict("os.environ", {"MANGA_TRANSLATOR_MODEL_DIR": str(model_dir)}):
            assert engine.is_available() is True

    def test_is_available_false_when_ckpt_missing(self, tmp_path: Path):
        """is_available returns False when the .ckpt file is absent."""
        model_dir = tmp_path / "models"
        model_dir.mkdir()
        # Only the alphabet file, no .ckpt
        (model_dir / "alphabet-all-v7.txt").write_text("a", encoding="utf-8")

        engine = MITOCREngine("48px")
        with patch.dict("os.environ", {"MANGA_TRANSLATOR_MODEL_DIR": str(model_dir)}):
            assert engine.is_available() is False


class TestMITOCREngineRegistry:
    """Tests for MIT engine registration in OCREngineRegistry.default()."""

    def test_default_registry_includes_mit_engines(self):
        """default() registers all 3 MIT OCR model variants."""
        registry = OCREngineRegistry.default()
        for model_name in MITOCREngine.supported_models():
            engine = registry.get(model_name)
            assert engine is not None, f"MIT OCR engine {model_name} not registered"
            assert engine.name == model_name

    def test_default_registry_list_engines_includes_mit(self):
        """list_engines() includes the MIT engines."""
        registry = OCREngineRegistry.default()
        names = [e["name"] for e in registry.list_engines()]
        assert "48px" in names
        assert "32px" in names
        assert "48px_ctc" in names

    def test_recovery_default_models_include_mit(self):
        """_DEFAULT_OCR_MODELS includes 48px/32px/48px_ctc with MIT descriptions."""
        from mga.ocr.recovery import _DEFAULT_OCR_MODELS

        names = [m["name"] for m in _DEFAULT_OCR_MODELS]
        assert "48px" in names
        assert "32px" in names
        assert "48px_ctc" in names
        # Descriptions now mention MIT runtime
        for model in _DEFAULT_OCR_MODELS:
            if model["name"] in ("48px", "32px", "48px_ctc"):
                assert "MIT" in model["description"], (
                    f"{model['name']} description should mention MIT"
                )
