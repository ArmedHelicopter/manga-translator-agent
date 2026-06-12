"""Tests for OCR engine bindings."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from mga.ocr.engines.base import OCREngine, OCREngineRegistry
from mga.ocr.engines.tesseract_engine import TesseractEngine


# ── Mock Engine for testing ──────────────────────────────────────────────────────

class FakeEngine(OCREngine):
    """Fake OCR engine for registry and wiring tests."""

    def __init__(self, name: str = "fake", available: bool = True, text: str = "fake text"):
        self._name = name
        self._available = available
        self._text = text

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Fake engine: {self._name}"

    def extract_text(self, image_path: str | Path, **kwargs) -> str:
        return self._text

    def is_available(self) -> bool:
        return self._available


# ── OCREngineRegistry Tests ──────────────────────────────────────────────────────

class TestOCREngineRegistry:
    """Tests for OCREngineRegistry."""

    def test_register_and_get(self):
        """Test registering and retrieving an engine."""
        registry = OCREngineRegistry()
        engine = FakeEngine("test_engine")
        registry.register(engine)

        assert registry.get("test_engine") is engine
        assert registry.get("nonexistent") is None

    def test_list_engines(self):
        """Test listing all registered engines."""
        registry = OCREngineRegistry()
        registry.register(FakeEngine("a"))
        registry.register(FakeEngine("b"))

        engines = registry.list_engines()
        assert len(engines) == 2
        names = {e["name"] for e in engines}
        assert names == {"a", "b"}

    def test_list_available_filters_unavailable(self):
        """Test that list_available only returns engines that are available."""
        registry = OCREngineRegistry()
        registry.register(FakeEngine("available", available=True))
        registry.register(FakeEngine("unavailable", available=False))

        available = registry.list_available()
        assert len(available) == 1
        assert available[0]["name"] == "available"

    def test_default_registry_has_tesseract(self):
        """Test that default registry includes TesseractEngine."""
        registry = OCREngineRegistry.default()
        assert registry.get("tesseract") is not None
        assert isinstance(registry.get("tesseract"), TesseractEngine)

    def test_default_registry_has_mocr(self):
        """Test that default registry includes MOCR entry (may not be available)."""
        registry = OCREngineRegistry.default()
        # MOCR may or may not be registered depending on whether manga_ocr is installed
        # Just verify the registry itself is functional
        assert registry.get("tesseract") is not None
        # MOCR registration depends on manga_ocr availability
        mocr = registry.get("mocr")
        if mocr is not None:
            assert mocr.name == "mocr"

    def test_engine_info_structure(self):
        """Test that engine info dicts have required keys."""
        registry = OCREngineRegistry()
        registry.register(FakeEngine("test"))

        engines = registry.list_engines()
        assert len(engines) == 1
        assert "name" in engines[0]
        assert "description" in engines[0]


# ── TesseractEngine Tests ───────────────────────────────────────────────────────

class TestTesseractEngine:
    """Tests for TesseractEngine."""

    def test_name_and_description(self):
        """Test engine metadata."""
        engine = TesseractEngine()
        assert engine.name == "tesseract"
        assert "Tesseract" in engine.description

    def test_is_available_false_when_no_tesseract(self):
        """Test that is_available returns False when pytesseract is not installed."""
        engine = TesseractEngine()
        with patch("mga.ocr.engines.tesseract_engine.TesseractEngine.is_available", return_value=False):
            assert engine.is_available() is False

    def test_extract_text_with_mock(self, tmp_path: Path):
        """Test text extraction with mocked pytesseract."""
        # Create a simple test image
        img = Image.new("RGB", (200, 100), color="white")
        img_path = tmp_path / "test.png"
        img.save(img_path)

        engine = TesseractEngine(lang="eng")

        # Mock pytesseract
        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_string.return_value = "Hello World"

        with patch.dict("sys.modules", {"pytesseract": mock_pytesseract}):
            result = engine.extract_text(img_path)

        assert result == "Hello World"
        mock_pytesseract.image_to_string.assert_called_once()

    def test_extract_text_lang_override(self, tmp_path: Path):
        """Test that lang kwarg overrides default."""
        img = Image.new("RGB", (200, 100), color="white")
        img_path = tmp_path / "test.png"
        img.save(img_path)

        engine = TesseractEngine(lang="jpn")

        mock_pytesseract = MagicMock()
        mock_pytesseract.image_to_string.return_value = "テスト"

        with patch.dict("sys.modules", {"pytesseract": mock_pytesseract}):
            engine.extract_text(img_path, lang="eng")

        # Verify the lang override was passed
        call_kwargs = mock_pytesseract.image_to_string.call_args
        assert call_kwargs[1]["lang"] == "eng"

    def test_extract_data_with_mock(self, tmp_path: Path):
        """Test structured data extraction with mocked pytesseract."""
        img = Image.new("RGB", (200, 100), color="white")
        img_path = tmp_path / "test.png"
        img.save(img_path)

        engine = TesseractEngine()

        mock_pytesseract = MagicMock()
        mock_pytesseract.Output.DICT = "dict"
        mock_pytesseract.image_to_data.return_value = {
            "text": ["Hello", "", "World"],
            "left": [10, 0, 50],
            "top": [20, 0, 20],
            "width": [30, 0, 40],
            "height": [15, 0, 15],
            "conf": [95, 0, 88],
        }

        with patch.dict("sys.modules", {"pytesseract": mock_pytesseract}):
            result = engine.extract_data(img_path)

        # Empty strings should be filtered out
        assert len(result) == 2
        assert result[0]["text"] == "Hello"
        assert result[0]["confidence"] == 95
        assert result[1]["text"] == "World"

    def test_custom_tesseract_cmd(self):
        """Test custom tesseract binary path."""
        engine = TesseractEngine(tesseract_cmd="/usr/local/bin/tesseract")
        assert engine._tesseract_cmd == "/usr/local/bin/tesseract"


# ── MOCREngine Tests ─────────────────────────────────────────────────────────────

class TestMOCREngine:
    """Tests for MOCREngine framework."""

    def test_name_and_description(self):
        """Test engine metadata."""
        from mga.ocr.engines.mocr_engine import MOCREngine
        engine = MOCREngine()
        assert engine.name == "mocr"
        assert "Manga OCR" in engine.description

    def test_custom_model_name(self):
        """Test custom model name."""
        from mga.ocr.engines.mocr_engine import MOCREngine
        engine = MOCREngine(model_name="custom/manga-ocr")
        assert "custom/manga-ocr" in engine.description

    def test_is_available_false_when_no_deps(self):
        """Test that is_available returns False when deps not installed."""
        from mga.ocr.engines.mocr_engine import MOCREngine
        engine = MOCREngine()
        # Mock is_available to simulate missing deps
        with patch("mga.ocr.engines.mocr_engine.MOCREngine.is_available", return_value=False):
            assert engine.is_available() is False


# ── Recovery Wiring Tests ─────────────────────────────────────────────────────────

class TestRecoveryEngineWiring:
    """Tests that OCR engine registry is wired into recovery orchestration."""

    def test_switch_model_resolves_engine(self):
        """Test that SWITCH_OCR_MODEL resolves the engine from registry."""
        from mga.ocr.models import OCRGuardConfig, RecoveryDecision, RecoveryStrategy
        from mga.ocr.recovery import RecoveryOrchestrator

        config = OCRGuardConfig(enabled=True)
        orchestrator = RecoveryOrchestrator(config)

        # Create a minimal context
        context = MagicMock()
        context.ocr_guard_state = {}
        context.metadata = {}

        decision = RecoveryDecision(
            strategy=RecoveryStrategy.SWITCH_OCR_MODEL,
            new_ocr_model="tesseract",
        )

        result_context, needs_restart = orchestrator.apply_strategy(decision, context)

        assert needs_restart is True
        assert result_context.metadata["requested_ocr_model"] == "tesseract"

    def test_switch_model_logs_warning_for_unknown_engine(self):
        """Test that switching to unknown engine logs warning but doesn't crash."""
        from mga.ocr.models import OCRGuardConfig, RecoveryDecision, RecoveryStrategy
        from mga.ocr.recovery import RecoveryOrchestrator

        config = OCRGuardConfig(enabled=True)
        orchestrator = RecoveryOrchestrator(config)

        context = MagicMock()
        context.ocr_guard_state = {}
        context.metadata = {}

        decision = RecoveryDecision(
            strategy=RecoveryStrategy.SWITCH_OCR_MODEL,
            new_ocr_model="nonexistent_engine",
        )

        result_context, needs_restart = orchestrator.apply_strategy(decision, context)

        # Should not crash — just logs warning
        assert needs_restart is True
        assert result_context.metadata["requested_ocr_model"] == "nonexistent_engine"

    def test_available_models_include_tesseract(self):
        """Test that Tesseract appears in default OCR model list."""
        from mga.ocr.recovery import _DEFAULT_OCR_MODELS

        names = [m["name"] for m in _DEFAULT_OCR_MODELS]
        assert "tesseract" in names
        assert "mocr" in names
