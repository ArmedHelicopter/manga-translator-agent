"""Project configuration data models."""

from __future__ import annotations

from typing import Dict, Optional

from pydantic import BaseModel, Field


class ProviderRoute(BaseModel):
    provider: str = ""
    model: str = ""


class StageProviderConfig(BaseModel):
    primary: ProviderRoute = Field(default_factory=ProviderRoute)
    fallback: Optional[ProviderRoute] = None
    local: Optional[ProviderRoute] = None


class ProjectConfig(BaseModel):
    project_name: str = "manga-project"
    source_lang: str = "ja"
    target_lang: str = "zh-CN"
    working_dir: str = ""
    output_dir: str = ""
    artifact_dir: str = ""
    input_format: str = "images"
    output_format: str = "images"
    pipeline_mode: str = "manga"
    reading_direction: str = "rtl"
    local_only: bool = False
    save_artifacts: bool = True
    save_debug_json: bool = False
    provider_routes: Dict[str, StageProviderConfig] = Field(default_factory=dict)
    provider_settings: Dict[str, dict] = Field(
        default_factory=dict,
        description="Per-provider kwargs (api_key, base_url, model, ...) for get_provider().",
    )
