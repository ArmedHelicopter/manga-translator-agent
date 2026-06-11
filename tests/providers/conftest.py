"""Shared fixtures for provider tests."""

from __future__ import annotations

import pytest

from mga.models import ProjectConfig
from mga.models.project import ProviderRoute, StageProviderConfig


@pytest.fixture
def vision_cfg_factory():
    """Factory for creating vision-configured ProjectConfig for tests."""
    def _make_cfg(model: str = "test-model", provider: str = "mimo"):
        return ProjectConfig(
            provider_routes={
                "vision": StageProviderConfig(
                    primary=ProviderRoute(provider=provider, model=model)
                ),
            },
            provider_settings={provider: {"api_key": "test-key", "vision_model": model}},
        )
    return _make_cfg