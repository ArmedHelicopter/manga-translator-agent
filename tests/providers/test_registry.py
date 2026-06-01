"""Tests for mga.providers.registry — provider registry and selection."""

import pytest

from mga.exceptions import ProviderError
from mga.models import ProjectConfig, ProviderRoute, StageProviderConfig
from mga.providers.cascade import ProviderCascade, resolve_provider_candidates
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


def test_resolve_provider_candidates_in_cascade_order():
    cfg = ProjectConfig(
        provider_routes={
            "translation": StageProviderConfig(
                primary=ProviderRoute(provider="primary", model="p-model"),
                fallback=ProviderRoute(provider="fallback", model="f-model"),
                local=ProviderRoute(provider="local", model="l-model"),
            )
        },
        provider_settings={
            "primary": {"api_key": "p"},
            "fallback": {"api_key": "f", "model": "existing"},
            "local": {},
        },
    )

    candidates = list(resolve_provider_candidates(cfg, "translation"))

    assert [candidate.role for candidate in candidates] == ["primary", "fallback", "local"]
    assert [candidate.provider for candidate in candidates] == ["primary", "fallback", "local"]
    assert candidates[0].settings["model"] == "p-model"
    assert candidates[1].settings["model"] == "existing"


def test_provider_cascade_uses_fallback_when_primary_fails(monkeypatch):
    class BrokenProvider:
        def chat(self, messages, **kwargs):
            raise RuntimeError("primary down")

    class WorkingProvider:
        def chat(self, messages, **kwargs):
            return "ok"

    def fake_get_provider(name, **kwargs):
        return BrokenProvider() if name == "primary" else WorkingProvider()

    monkeypatch.setattr("mga.providers.cascade.get_provider", fake_get_provider)
    cfg = ProjectConfig(
        provider_routes={
            "translation": StageProviderConfig(
                primary=ProviderRoute(provider="primary"),
                fallback=ProviderRoute(provider="fallback"),
            )
        },
    )

    cascade = ProviderCascade(cfg, "translation")
    raw, candidate = cascade.call_chat(
        [{"role": "user", "content": "x"}],
        operation="semantic_translation",
        trace_context={"bubble_id": "b1"},
    )

    assert raw == "ok"
    assert candidate.provider == "fallback"
    assert cascade.calls == [
        {
            "bubble_id": "b1",
            "operation": "semantic_translation",
            "role": "fallback",
            "provider": "fallback",
            "model": "",
        }
    ]
    assert cascade.errors[0]["provider"] == "primary"
    assert cascade.errors[0]["bubble_id"] == "b1"
