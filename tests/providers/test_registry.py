"""Tests for mga.providers.registry — provider registry and selection."""

import pytest

from mga.exceptions import ProviderError
from mga.models import ProjectConfig, ProviderRoute, StageProviderConfig
from mga.providers import registry
from mga.providers.cascade import ProviderCascade, ProviderCascadeAdapter, resolve_provider_candidates
from mga.providers.registry import get_provider, select_provider


def test_registry_exposes_documented_provider_map():
    assert registry._PROVIDER_MAP == {
        "openai": (".openai_provider", "OpenAIProvider"),
        "anthropic": (".anthropic_provider", "AnthropicProvider"),
        "gemini": (".gemini_provider", "GeminiProvider"),
        "deepseek": (".deepseek_provider", "DeepSeekProvider"),
        "ollama": (".ollama_provider", "OllamaProvider"),
        "lmstudio": (".lmstudio_provider", "LMStudioProvider"),
        "vllm": (".vllm_provider", "VLLMProvider"),
        "openrouter": (".openrouter_provider", "OpenRouterProvider"),
        "llamacpp": (".llamacpp_provider", "LlamaCppProvider"),
    }


def test_get_provider_openai():
    provider = get_provider("openai", api_key="test-key")
    assert provider is not None
    assert provider.__class__.__name__ == "OpenAIProvider"


def test_get_provider_mimo_uses_openai_compatible_defaults(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("MIMO_API_KEY", "mimo-key")
    monkeypatch.setattr("mga.providers.openai_provider.openai.OpenAI", FakeOpenAI)

    provider = get_provider("mimo")

    assert provider.__class__.__name__ == "OpenAIProvider"
    assert provider.model_name == "mimo-v2.5"
    assert captured["api_key"] == "mimo-key"
    assert str(captured["base_url"]) == "https://token-plan-cn.xiaomimimo.com/v1"


def test_get_provider_uses_openai_compatible_provider_type(monkeypatch):
    captured = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("COMPAT_KEY", "compat-key")
    monkeypatch.setattr("mga.providers.openai_provider.openai.OpenAI", FakeOpenAI)

    provider = get_provider(
        "custom_compatible",
        provider_type="openai",
        api_key_env="COMPAT_KEY",
        base_url="https://compatible.example/v1",
        vision_model="vision-model",
        text_model="text-model",
    )

    assert provider.__class__.__name__ == "OpenAIProvider"
    assert provider.model_name == "vision-model"
    assert provider._translate_model == "text-model"
    assert captured["api_key"] == "compat-key"
    assert str(captured["base_url"]) == "https://compatible.example/v1"


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


def test_select_provider_loads_plugin_provider_class(tmp_path, monkeypatch):
    plugin_module = tmp_path / "custom_provider.py"
    plugin_module.write_text(
        """
from mga.providers.base import LLMProvider


class CustomProvider(LLMProvider):
    def __init__(self, model="", greeting=""):
        self._model = model
        self.greeting = greeting

    @property
    def model_name(self):
        return self._model

    @property
    def supports_vision(self):
        return False

    @property
    def cost_per_1k_tokens(self):
        return None

    def chat(self, messages, **kwargs):
        return f"{self.greeting}:{self._model}:{messages[-1]['content']}"

    def chat_structured(self, messages, schema, **kwargs):
        return {"text": self.chat(messages)}

    def vision(self, messages, images, **kwargs):
        raise NotImplementedError

    def vision_structured(self, messages, images, schema, **kwargs):
        raise NotImplementedError
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    config = {
        "stages": {"translation": {"primary": "custom_engine"}},
        "providers": {
            "custom_engine": {
                "plugin": "custom_provider:CustomProvider",
                "model": "plugin-model",
                "greeting": "hello",
            }
        },
    }

    provider = select_provider("translation", config)

    assert provider.model_name == "plugin-model"
    assert provider.chat([{"role": "user", "content": "source"}]) == "hello:plugin-model:source"


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


def test_select_provider_falls_back_with_configured_settings(monkeypatch):
    calls = []

    class DummyProvider:
        def __init__(self, name, settings):
            self.name = name
            self.settings = settings

    def fake_get_provider(name, **kwargs):
        calls.append((name, kwargs))
        if name == "primary":
            raise RuntimeError("primary down")
        return DummyProvider(name, kwargs)

    monkeypatch.setattr("mga.providers.registry.get_provider", fake_get_provider)
    config = {
        "stages": {
            "qa": {
                "primary": "primary",
                "fallback": "fallback",
                "local": "local",
            }
        },
        "providers": {
            "primary": {"api_key": "primary-key"},
            "fallback": {"api_key": "fallback-key", "model": "fallback-model"},
            "local": {"base_url": "http://localhost:11434"},
        },
    }

    provider = select_provider("qa", config)

    assert provider.name == "fallback"
    assert provider.settings == {"api_key": "fallback-key", "model": "fallback-model"}
    assert calls == [
        ("primary", {"api_key": "primary-key"}),
        ("fallback", {"api_key": "fallback-key", "model": "fallback-model"}),
    ]


def test_select_provider_falls_back_for_runtime_chat_failure(monkeypatch):
    calls = []

    class BrokenProvider:
        def chat(self, messages, **kwargs):
            raise RuntimeError("primary runtime down")

    class WorkingProvider:
        def chat(self, messages, **kwargs):
            return "ok"

    def fake_get_provider(name, **kwargs):
        calls.append((name, kwargs))
        return BrokenProvider() if name == "primary" else WorkingProvider()

    monkeypatch.setattr("mga.providers.registry.get_provider", fake_get_provider)
    config = {
        "stages": {
            "qa": {
                "primary": "primary",
                "fallback": "fallback",
            }
        },
        "providers": {
            "primary": {"api_key": "primary-key"},
            "fallback": {"api_key": "fallback-key"},
        },
    }

    provider = select_provider("qa", config)

    assert provider.chat([{"role": "user", "content": "x"}]) == "ok"
    assert calls == [
        ("primary", {"api_key": "primary-key"}),
        ("fallback", {"api_key": "fallback-key"}),
    ]


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


def test_resolve_provider_candidates_keeps_same_provider_with_different_models():
    cfg = ProjectConfig(
        provider_routes={
            "translation": StageProviderConfig(
                primary=ProviderRoute(provider="openai", model="expensive-model"),
                fallback=ProviderRoute(provider="openai", model="cheap-model"),
                local=ProviderRoute(provider="openai", model="local-model"),
            )
        },
        provider_settings={"openai": {"api_key": "secret"}},
    )

    candidates = list(resolve_provider_candidates(cfg, "translation"))

    assert [candidate.role for candidate in candidates] == ["primary", "fallback", "local"]
    assert [candidate.provider for candidate in candidates] == ["openai", "openai", "openai"]
    assert [candidate.settings["model"] for candidate in candidates] == [
        "expensive-model",
        "cheap-model",
        "local-model",
    ]


def test_resolve_provider_candidates_dedupes_exact_same_provider_settings():
    cfg = ProjectConfig(
        provider_routes={
            "translation": StageProviderConfig(
                primary=ProviderRoute(provider="openai", model="same-model"),
                fallback=ProviderRoute(provider="openai", model="same-model"),
            )
        },
        provider_settings={"openai": {"api_key": "secret"}},
    )

    candidates = list(resolve_provider_candidates(cfg, "translation"))

    assert [candidate.role for candidate in candidates] == ["primary"]
    assert candidates[0].settings["model"] == "same-model"


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


def test_provider_cascade_falls_back_between_models_for_same_provider(monkeypatch):
    class ModelAwareProvider:
        def __init__(self, model: str) -> None:
            self.model = model

        def chat(self, messages, **kwargs):
            if self.model == "primary-model":
                raise RuntimeError("primary model down")
            return f"ok:{self.model}"

    def fake_get_provider(name, **kwargs):
        assert name == "openai"
        return ModelAwareProvider(kwargs.get("model", ""))

    monkeypatch.setattr("mga.providers.cascade.get_provider", fake_get_provider)
    cfg = ProjectConfig(
        provider_routes={
            "translation": StageProviderConfig(
                primary=ProviderRoute(provider="openai", model="primary-model"),
                fallback=ProviderRoute(provider="openai", model="fallback-model"),
            )
        },
    )

    cascade = ProviderCascade(cfg, "translation")
    raw, candidate = cascade.call_chat(
        [{"role": "user", "content": "x"}],
        operation="semantic_translation",
    )

    assert raw == "ok:fallback-model"
    assert candidate.role == "fallback"
    assert candidate.provider == "openai"
    assert candidate.model == "fallback-model"
    assert cascade.errors[0]["role"] == "primary"
    assert cascade.calls == [
        {
            "operation": "semantic_translation",
            "role": "fallback",
            "provider": "openai",
            "model": "fallback-model",
        }
    ]


def test_provider_cascade_adapter_falls_back_for_chat_structured_runtime_failure():
    class BrokenProvider:
        def chat_structured(self, **kwargs):
            raise RuntimeError("primary runtime down")

    class WorkingProvider:
        def chat_structured(self, **kwargs):
            return {"ok": True}

    cfg = ProjectConfig(
        provider_routes={
            "translation": StageProviderConfig(
                primary=ProviderRoute(provider="primary"),
                fallback=ProviderRoute(provider="fallback"),
            )
        },
    )
    cascade = ProviderCascade(cfg, "translation")
    adapter = ProviderCascadeAdapter(
        cascade,
        [
            (cascade.candidates[0], BrokenProvider()),
            (cascade.candidates[1], WorkingProvider()),
        ],
    )

    raw = adapter.chat_structured(
        messages=[{"role": "user", "content": "x"}],
        schema={"type": "object"},
        operation="learning_pattern_extract",
    )

    assert raw == {"ok": True}
    assert cascade.errors[0]["provider"] == "primary"
    assert cascade.errors[0]["operation"] == "learning_pattern_extract"
    assert cascade.calls == [
        {
            "operation": "learning_pattern_extract",
            "role": "fallback",
            "provider": "fallback",
            "model": "",
        }
    ]


def test_provider_cascade_adapter_falls_back_for_vision_extract_runtime_failure():
    class BrokenProvider:
        def vision_extract(self, *args, **kwargs):
            raise RuntimeError("primary runtime down")

    class WorkingProvider:
        def vision_extract(self, *args, **kwargs):
            return ("page", "trace")

    cfg = ProjectConfig(
        provider_routes={
            "vision": StageProviderConfig(
                primary=ProviderRoute(provider="primary"),
                fallback=ProviderRoute(provider="fallback"),
            )
        },
    )
    cascade = ProviderCascade(cfg, "vision")
    adapter = ProviderCascadeAdapter(
        cascade,
        [
            (cascade.candidates[0], BrokenProvider()),
            (cascade.candidates[1], WorkingProvider()),
        ],
    )

    result = adapter.vision_extract("page", store="store")

    assert result == ("page", "trace")
    assert cascade.errors[0]["provider"] == "primary"
    assert cascade.errors[0]["operation"] == "vision_extract"
    assert cascade.calls == [
        {
            "operation": "vision_extract",
            "role": "fallback",
            "provider": "fallback",
            "model": "",
        }
    ]


def test_provider_cascade_adapter_falls_back_for_translate_runtime_failure():
    class BrokenProvider:
        def translate(self, *args, **kwargs):
            raise RuntimeError("primary runtime down")

    class WorkingProvider:
        def translate(self, *args, **kwargs):
            return (["translated"], "trace")

    cfg = ProjectConfig(
        provider_routes={
            "translation": StageProviderConfig(
                primary=ProviderRoute(provider="primary"),
                fallback=ProviderRoute(provider="fallback"),
            )
        },
    )
    cascade = ProviderCascade(cfg, "translation")
    adapter = ProviderCascadeAdapter(
        cascade,
        [
            (cascade.candidates[0], BrokenProvider()),
            (cascade.candidates[1], WorkingProvider()),
        ],
    )

    result = adapter.translate("page", ["utterance"], store="store")

    assert result == (["translated"], "trace")
    assert cascade.errors[0]["provider"] == "primary"
    assert cascade.errors[0]["operation"] == "translate"
    assert cascade.calls == [
        {
            "operation": "translate",
            "role": "fallback",
            "provider": "fallback",
            "model": "",
        }
    ]


def test_provider_cascade_adapter_falls_back_for_direct_translate_page_runtime_failure():
    class BrokenProvider:
        def direct_translate_page(self, *args, **kwargs):
            raise RuntimeError("primary runtime down")

    class WorkingProvider:
        def direct_translate_page(self, *args, **kwargs):
            return (["direct"], "trace")

    cfg = ProjectConfig(
        provider_routes={
            "translation": StageProviderConfig(
                primary=ProviderRoute(provider="primary"),
                fallback=ProviderRoute(provider="fallback"),
            )
        },
    )
    cascade = ProviderCascade(cfg, "translation")
    adapter = ProviderCascadeAdapter(
        cascade,
        [
            (cascade.candidates[0], BrokenProvider()),
            (cascade.candidates[1], WorkingProvider()),
        ],
    )

    result = adapter.direct_translate_page("page", store="store")

    assert result == (["direct"], "trace")
    assert cascade.errors[0]["provider"] == "primary"
    assert cascade.errors[0]["operation"] == "direct_translate_page"
    assert cascade.calls == [
        {
            "operation": "direct_translate_page",
            "role": "fallback",
            "provider": "fallback",
            "model": "",
        }
    ]
