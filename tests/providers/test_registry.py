"""Tests for mga.providers.registry — provider registry and selection."""

import pytest

from mga.exceptions import ProviderError
from mga.providers.registry import get_provider, select_provider


def test_get_provider_openai():
    provider = get_provider("openai", api_key="test-key")
    assert provider is not None
    assert provider.__class__.__name__ == "OpenAIProvider"


def test_get_provider_anthropic():
    try:
        provider = get_provider("anthropic", api_key="test-key")
        assert provider is not None
        assert provider.__class__.__name__ == "AnthropicProvider"
    except ImportError:
        pytest.skip("anthropic package not installed")


def test_get_provider_ollama():
    provider = get_provider("ollama")
    assert provider is not None
    assert provider.__class__.__name__ == "OllamaProvider"


def test_get_provider_unknown():
    with pytest.raises(ProviderError, match="Unknown provider"):
        get_provider("nonexistent_provider")


def test_select_provider_primary():
    config = {
        "stages": {"vision": {"primary": "openai"}},
        "providers": {"openai": {"api_key": "test"}},
    }
    provider = select_provider("vision", config)
    assert provider is not None


def test_select_provider_force_local():
    config = {
        "stages": {"vision": {"local": "ollama"}},
        "providers": {},
    }
    provider = select_provider("vision", config, force_local=True)
    assert provider is not None


def test_select_provider_force_local_no_local():
    config = {"stages": {"vision": {}}, "providers": {}}
    with pytest.raises(ProviderError, match="No local provider"):
        select_provider("vision", config, force_local=True)


def test_select_provider_no_provider():
    config = {"stages": {"vision": {}}, "providers": {}}
    with pytest.raises(ProviderError, match="No provider available"):
        select_provider("vision", config)
