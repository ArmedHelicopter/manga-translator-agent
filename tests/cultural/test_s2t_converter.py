"""Tests for S2TConverter (Simplified/Traditional Chinese conversion)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mga.cultural.s2t_converter import S2TConverter, _CONVERSIONS


class TestS2TConverterBasics:
    """Tests for S2TConverter basic behavior."""

    def test_auto_variant_is_noop(self):
        """variant='auto' returns text unchanged and is not available."""
        converter = S2TConverter("auto")
        assert converter.available is False
        assert converter.convert("测试") == "测试"

    def test_empty_variant_is_noop(self):
        """Empty variant returns text unchanged."""
        converter = S2TConverter("")
        assert converter.available is False
        assert converter.convert("测试") == "测试"

    def test_none_variant_is_noop(self):
        """None variant returns text unchanged."""
        converter = S2TConverter(None)
        assert converter.available is False
        assert converter.convert("测试") == "测试"

    def test_variant_property(self):
        """variant property returns the configured variant."""
        assert S2TConverter("s2t").variant == "s2t"
        assert S2TConverter("t2s").variant == "t2s"

    def test_conversions_dict_has_all_variants(self):
        """_CONVERSIONS has all 4 conversion variants."""
        assert "s2t" in _CONVERSIONS
        assert "t2s" in _CONVERSIONS
        assert "tw" in _CONVERSIONS
        assert "hk" in _CONVERSIONS


class TestS2TConverterWithoutOpencc:
    """Tests for graceful degradation when opencc is not installed."""

    def test_convert_without_opencc_is_noop(self):
        """When opencc is not installed, convert() returns original text."""
        converter = S2TConverter("s2t")
        # If opencc is not installed, _available is False and convert is no-op
        if not converter.available:
            assert converter.convert("测试") == "测试"

    def test_unknown_variant_does_not_crash(self):
        """Unknown variant logs a warning and is a no-op."""
        converter = S2TConverter("invalid_variant")
        assert converter.available is False
        # Should not raise
        assert converter.convert("测试") == "测试"

    def test_convert_empty_text(self):
        """Empty/None text returns unchanged."""
        converter = S2TConverter("s2t")
        assert converter.convert("") == ""
        assert converter.convert(None) is None


class TestS2TConverterWithMockedOpencc:
    """Tests with mocked opencc module."""

    def test_convert_s2t(self):
        """S2T variant calls opencc with 's2t' config."""
        mock_opencc = MagicMock()
        mock_converter = MagicMock()
        mock_converter.convert.return_value = "測試"
        mock_opencc.OpenCC.return_value = mock_converter

        with patch.dict("sys.modules", {"opencc": mock_opencc}):
            converter = S2TConverter("s2t")
            assert converter.available is True
            result = converter.convert("测试")
            assert result == "測試"
            mock_opencc.OpenCC.assert_called_once_with("s2t")
            mock_converter.convert.assert_called_once_with("测试")

    def test_convert_t2s(self):
        """T2S variant calls opencc with 't2s' config."""
        mock_opencc = MagicMock()
        mock_converter = MagicMock()
        mock_converter.convert.return_value = "测试"
        mock_opencc.OpenCC.return_value = mock_converter

        with patch.dict("sys.modules", {"opencc": mock_opencc}):
            converter = S2TConverter("t2s")
            assert converter.available is True
            result = converter.convert("測試")
            assert result == "测试"
            mock_opencc.OpenCC.assert_called_once_with("t2s")

    def test_convert_tw(self):
        """TW variant calls opencc with 's2tw' config."""
        mock_opencc = MagicMock()
        mock_converter = MagicMock()
        mock_converter.convert.return_value = "測試"
        mock_opencc.OpenCC.return_value = mock_converter

        with patch.dict("sys.modules", {"opencc": mock_opencc}):
            converter = S2TConverter("tw")
            result = converter.convert("测试")
            mock_opencc.OpenCC.assert_called_once_with("s2tw")

    def test_convert_hk(self):
        """HK variant calls opencc with 's2hk' config."""
        mock_opencc = MagicMock()
        mock_converter = MagicMock()
        mock_converter.convert.return_value = "測試"
        mock_opencc.OpenCC.return_value = mock_converter

        with patch.dict("sys.modules", {"opencc": mock_opencc}):
            converter = S2TConverter("hk")
            result = converter.convert("测试")
            mock_opencc.OpenCC.assert_called_once_with("s2hk")

    def test_convert_failure_returns_original(self):
        """If opencc.convert() raises, returns original text."""
        mock_opencc = MagicMock()
        mock_converter = MagicMock()
        mock_converter.convert.side_effect = RuntimeError("conversion failed")
        mock_opencc.OpenCC.return_value = mock_converter

        with patch.dict("sys.modules", {"opencc": mock_opencc}):
            converter = S2TConverter("s2t")
            assert converter.available is True
            result = converter.convert("测试")
            assert result == "测试"  # original returned on failure


class TestProjectConfigChineseVariant:
    """Tests for ProjectConfig.chinese_variant field."""

    def test_default_chinese_variant(self):
        from mga.models.project import ProjectConfig
        cfg = ProjectConfig()
        assert cfg.chinese_variant == "auto"

    def test_custom_chinese_variant(self):
        from mga.models.project import ProjectConfig
        cfg = ProjectConfig(chinese_variant="s2t")
        assert cfg.chinese_variant == "s2t"


class TestRenderStageS2TIntegration:
    """Tests for S2T integration in RenderStage."""

    def test_get_s2t_converter_auto_returns_none(self):
        """_get_s2t_converter returns None for 'auto' variant."""
        from mga.models.project import ProjectConfig
        from mga.pipeline.render_stage import RenderStage
        cfg = ProjectConfig()
        assert RenderStage._get_s2t_converter(cfg) is None

    def test_get_s2t_converter_s2t_returns_converter(self):
        """_get_s2t_converter returns a converter for 's2t' variant."""
        from mga.models.project import ProjectConfig
        from mga.pipeline.render_stage import RenderStage
        cfg = ProjectConfig(chinese_variant="s2t")
        converter = RenderStage._get_s2t_converter(cfg)
        assert converter is not None
        assert converter.variant == "s2t"

    def test_get_s2t_converter_caches(self):
        """_get_s2t_converter caches the converter."""
        from mga.models.project import ProjectConfig
        from mga.pipeline.render_stage import RenderStage
        # Clear cache
        if hasattr(RenderStage, "_s2t_converter_cache"):
            del RenderStage._s2t_converter_cache
        cfg = ProjectConfig(chinese_variant="s2t")
        converter1 = RenderStage._get_s2t_converter(cfg)
        converter2 = RenderStage._get_s2t_converter(cfg)
        assert converter1 is converter2  # Same instance (cached)
