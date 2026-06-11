"""Tests for mga.providers.vision_probe and CLI vision pre-check."""

from __future__ import annotations

import click
import pytest

from mga.cli.main import _check_vision_provider_capability
from mga.models import ProjectConfig, ProviderRoute, StageProviderConfig
from mga.providers import vision_probe
from mga.providers.vision_probe import (
    TINY_PNG,
    discover_vision_models,
    is_image_rejection_error,
    probe_vision,
)


class FakeProvider:
    def __init__(self, *, vision_ok=True, error="", supports_vision=True, model="m"):
        self._vision_ok = vision_ok
        self._error = error
        self.supports_vision = supports_vision
        self.model_name = model
        self.vision_calls = []

    def vision(self, messages, images, **kwargs):
        self.vision_calls.append((messages, images))
        if not self._vision_ok:
            raise RuntimeError(self._error or "boom")
        return "OK"


# -- probe_vision -----------------------------------------------------------


def test_probe_vision_success():
    provider = FakeProvider(vision_ok=True)
    ok, err = probe_vision(provider)
    assert ok is True
    assert err == ""
    # The probe must send the tiny PNG.
    assert provider.vision_calls[0][1] == [TINY_PNG]


def test_probe_vision_failure_returns_error():
    provider = FakeProvider(vision_ok=False, error="No endpoints found that support image input")
    ok, err = probe_vision(provider)
    assert ok is False
    assert "image input" in err


def test_probe_vision_respects_supports_vision_false():
    provider = FakeProvider(supports_vision=False)
    ok, err = probe_vision(provider)
    assert ok is False
    assert provider.vision_calls == []
    assert is_image_rejection_error(err)


# -- is_image_rejection_error -----------------------------------------------


@pytest.mark.parametrize(
    "message",
    [
        "Error code: 404 - No endpoints found that support image input",
        "model X does not support image inputs",
        "vision is not supported for this model",
    ],
)
def test_is_image_rejection_error_positive(message):
    assert is_image_rejection_error(message) is True


@pytest.mark.parametrize(
    "message",
    ["Invalid API Key", "Connection timed out", "rate limit exceeded"],
)
def test_is_image_rejection_error_negative(message):
    assert is_image_rejection_error(message) is False


# -- discover_vision_models --------------------------------------------------


def test_discover_vision_models_probes_siblings(monkeypatch):
    """Sibling chat models are probed; tts/asr models are skipped; capable ones returned."""
    listed = ["mimo-v2.5", "mimo-v2.5-tts", "mimo-v2.5-asr", "mimo-v2-omni", "mimo-v2.5-pro"]
    vision_capable = {"mimo-v2.5", "mimo-v2-omni"}
    created = []

    class FakeListedProvider:
        def __init__(self, model):
            self.model_name = model
            self.supports_vision = True

        def vision(self, messages, images, **kwargs):
            if self.model_name not in vision_capable:
                raise RuntimeError("No endpoints found that support image input")
            return "OK"

    def fake_get_provider(name, **settings):
        model = settings.get("vision_model") or settings.get("model") or "base"
        provider = FakeListedProvider(model)
        created.append((name, model))
        return provider

    monkeypatch.setattr("mga.providers.registry.get_provider", fake_get_provider)
    monkeypatch.setattr(vision_probe, "list_models", lambda provider: listed)

    result = discover_vision_models(
        "mimo", {"api_key": "k"}, current_model="mimo-v2.5-pro"
    )

    assert result == ["mimo-v2.5", "mimo-v2-omni"]
    probed_models = {model for _name, model in created if model != "base"}
    # Non-chat models must not be probed.
    assert not any("tts" in m or "asr" in m for m in probed_models)
    # Closest name to current model should be probed (and ranked) first.
    assert result[0] == "mimo-v2.5"


def test_discover_vision_models_handles_provider_instantiation_failure(monkeypatch):
    def failing_get_provider(name, **settings):
        raise RuntimeError("no api key")

    monkeypatch.setattr("mga.providers.registry.get_provider", failing_get_provider)
    assert discover_vision_models("mimo", {}, current_model="x") == []


# -- CLI _check_vision_provider_capability ------------------------------------


def _vision_cfg(model: str = "text-only-model") -> ProjectConfig:
    return ProjectConfig(
        provider_routes={
            "vision": StageProviderConfig(primary=ProviderRoute(provider="mimo", model=model)),
        },
        provider_settings={"mimo": {"api_key": "k", "vision_model": model}},
    )


def test_vision_precheck_passes_when_capable(monkeypatch):
    cfg = _vision_cfg()
    monkeypatch.setattr("mga.providers.factory.create_provider", lambda name, settings=None, **kw: FakeProvider())
    _check_vision_provider_capability(cfg)  # should not raise


def test_vision_precheck_fails_with_suggestions(monkeypatch):
    cfg = _vision_cfg("text-only-model")
    monkeypatch.setattr(
        "mga.providers.factory.create_provider",
        lambda name, settings=None, **kw: FakeProvider(
            vision_ok=False, error="No endpoints found that support image input"
        ),
    )
    monkeypatch.setattr(
        "mga.providers.vision_probe.discover_vision_models",
        lambda *a, **kw: ["vision-model-a", "vision-model-b"],
    )

    with pytest.raises(click.ClickException) as excinfo:
        _check_vision_provider_capability(cfg)

    message = str(excinfo.value.message)
    assert "text-only-model" in message
    assert "vision-model-a" in message
    assert "--auto-vision-model" in message


def test_vision_precheck_fails_without_suggestions(monkeypatch):
    cfg = _vision_cfg()
    monkeypatch.setattr(
        "mga.providers.factory.create_provider",
        lambda name, settings=None, **kw: FakeProvider(
            vision_ok=False, error="does not support image inputs"
        ),
    )
    monkeypatch.setattr(
        "mga.providers.vision_probe.discover_vision_models", lambda *a, **kw: []
    )

    with pytest.raises(click.ClickException) as excinfo:
        _check_vision_provider_capability(cfg)
    assert "vision-capable provider" in str(excinfo.value.message)


def test_vision_precheck_auto_switches_when_flag_set(monkeypatch):
    cfg = _vision_cfg("text-only-model")
    monkeypatch.setattr(
        "mga.providers.factory.create_provider",
        lambda name, settings=None, **kw: FakeProvider(
            vision_ok=False, error="No endpoints found that support image input"
        ),
    )
    monkeypatch.setattr(
        "mga.providers.vision_probe.discover_vision_models",
        lambda *a, **kw: ["vision-model-a", "vision-model-b"],
    )

    _check_vision_provider_capability(cfg, auto_vision_model=True)

    assert cfg.provider_settings["mimo"]["vision_model"] == "vision-model-a"
    assert cfg.provider_routes["vision"].primary.model == "vision-model-a"


def test_vision_precheck_inconclusive_on_transient_error(monkeypatch):
    """Auth/connectivity failures must not abort the run (cascade handles them)."""
    cfg = _vision_cfg()
    monkeypatch.setattr(
        "mga.providers.factory.create_provider",
        lambda name, settings=None, **kw: FakeProvider(vision_ok=False, error="Invalid API Key"),
    )
    _check_vision_provider_capability(cfg)  # should not raise


def test_vision_precheck_no_vision_route_is_noop():
    cfg = ProjectConfig(provider_routes={}, provider_settings={})
    # No vision stage configured -> cascade falls back to default openai candidate;
    # ensure no exception when provider instantiation fails (recorded as probe error).
    _check_vision_provider_capability(cfg)
