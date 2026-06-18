"""Tests for lazy provider registry (AST-scan metadata discovery)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mga.providers.lazy_registry import (
    ProviderSpec,
    get_lazy_provider_info,
    get_provider_specs,
    list_lazy_providers,
    scan_provider_metadata,
)


class TestScanProviderMetadata:
    """Tests for scan_provider_metadata (AST scanning without imports)."""

    def test_scan_finds_all_provider_modules(self):
        """AST scan finds all *_provider.py modules."""
        specs = scan_provider_metadata()
        # openai and cohere have PROVIDER_METADATA; others fall back to _PROVIDER_MAP
        assert "openai" in specs
        assert "cohere" in specs

    def test_scan_openai_metadata(self):
        """OpenAI metadata has correct fields."""
        specs = scan_provider_metadata()
        openai = specs["openai"]
        assert openai.name == "openai"
        assert openai.class_name == "OpenAIProvider"
        assert openai.vision is True
        assert openai.structured == "json_mode"
        assert openai.notes is not None

    def test_scan_cohere_metadata(self):
        """Cohere metadata has correct fields."""
        specs = scan_provider_metadata()
        cohere = specs["cohere"]
        assert cohere.name == "cohere"
        assert cohere.class_name == "CohereProvider"
        assert cohere.vision is True

    def test_scan_does_not_import_modules(self):
        """AST scan does not import provider modules (no SDK side effects)."""
        # Remove any cached provider modules
        for key in list(sys.modules):
            if key.startswith("mga.providers.") and key.endswith("_provider"):
                del sys.modules[key]

        scan_provider_metadata()

        # None of the provider modules should be in sys.modules after scan
        for key in sys.modules:
            if key.startswith("mga.providers.") and key.endswith("_provider"):
                pytest.fail(f"Provider module {key} was imported during scan")

    def test_scan_syntax_error_skipped(self, tmp_path: Path):
        """Modules with syntax errors are skipped, not crash."""
        # Create a fake provider module with a syntax error
        fake = tmp_path / "fake_provider.py"
        fake.write_text("PROVIDER_METADATA = {", encoding="utf-8")  # incomplete dict

        specs = scan_provider_metadata(tmp_path)
        # Should not crash, just skip
        assert "fake" not in specs


class TestGetProviderSpecs:
    """Tests for get_provider_specs (merged _PROVIDER_MAP + AST scan)."""

    def test_get_provider_specs_includes_all_provider_map_entries(self):
        """get_provider_specs includes every _PROVIDER_MAP entry as base."""
        from mga.providers.factory import _PROVIDER_MAP

        specs = get_provider_specs()
        for name in _PROVIDER_MAP:
            assert name in specs, f"{name} missing from get_provider_specs"
            assert specs[name].class_name == _PROVIDER_MAP[name][1]

    def test_get_provider_specs_merges_ast_metadata(self):
        """AST metadata (vision/structured/notes) is merged into base specs."""
        specs = get_provider_specs()
        # openai has PROVIDER_METADATA with vision=True
        assert specs["openai"].vision is True
        assert specs["openai"].structured == "json_mode"

    def test_get_provider_specs_cached(self):
        """get_provider_specs is cached (lru_cache)."""
        specs1 = get_provider_specs()
        specs2 = get_provider_specs()
        assert specs1 is specs2  # Same object (cached)


class TestListLazyProviders:
    """Tests for list_lazy_providers."""

    def test_list_lazy_providers_includes_all(self):
        """list_lazy_providers includes all _PROVIDER_MAP names."""
        from mga.providers.factory import _PROVIDER_MAP

        names = list_lazy_providers()
        for name in _PROVIDER_MAP:
            assert name in names


class TestGetLazyProviderInfo:
    """Tests for get_lazy_provider_info."""

    def test_get_lazy_provider_info_openai(self):
        """get_lazy_provider_info returns metadata for openai."""
        info = get_lazy_provider_info("openai")
        assert info is not None
        assert info["name"] == "openai"
        assert info["class"] == "OpenAIProvider"
        assert info["vision"] is True

    def test_get_lazy_provider_info_unknown_returns_none(self):
        """get_lazy_provider_info returns None for unknown provider."""
        assert get_lazy_provider_info("nonexistent_provider") is None

    def test_get_lazy_provider_info_case_insensitive(self):
        """get_lazy_provider_info is case-insensitive."""
        info = get_lazy_provider_info("OpenAI")
        assert info is not None
        assert info["name"] == "openai"


class TestBackwardCompat:
    """Tests that lazy registry does not break existing provider loading."""

    def test_get_provider_still_works(self):
        """get_provider('openai') still returns OpenAIProvider (backward compat)."""
        from mga.providers.factory import get_provider

        provider = get_provider("openai", api_key="test-key")
        assert provider.__class__.__name__ == "OpenAIProvider"

    def test_list_all_providers_unchanged(self):
        """list_all_providers returns same names as before."""
        from mga.providers.factory import list_all_providers, _PROVIDER_MAP, _PROVIDER_PROFILES

        all_names = set(list_all_providers())
        expected = set(_PROVIDER_MAP.keys()) | set(_PROVIDER_PROFILES.keys())
        assert all_names == expected

    def test_registry_exposes_documented_provider_map(self):
        """Existing test: _PROVIDER_MAP contents unchanged."""
        from mga.providers.factory import _PROVIDER_MAP

        # Spot-check a few entries
        assert _PROVIDER_MAP["openai"] == (".openai_provider", "OpenAIProvider")
        assert _PROVIDER_MAP["cohere"] == (".cohere_provider", "CohereProvider")
        assert _PROVIDER_MAP["groq"] == (".groq_provider", "GroqProvider")
