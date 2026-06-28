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
    plugins: Dict[str, dict] = Field(
        default_factory=dict,
        description="Project-local plugin configuration for extension points.",
    )
    # Pipeline optimization settings
    parallel_mode: str = "serial"  # serial | parallel | pipelined
    pipeline_concurrency: int = 5  # Max pages in flight
    translation_max_workers: int = 3  # Per-page bubble concurrency
    llm_cache_enabled: bool = True
    llm_cache_dir: str = ".mga_cache"
    translation_config: dict = Field(
        default_factory=dict,
        description="Translation pipeline config from TOML (populated by loader)",
    )
    # OCR guard configuration (dict or OCRGuardConfig instance)
    ocr_guard: Optional[dict] = Field(
        default=None,
        description="OCR blank-page detection and recovery config.",
    )
    # Inpaint backend for manga-image-translator runtime.
    # Maps to the runtime's Inpainter enum: auto|none|lama_large|lama_mpe|sd|original|default
    inpaint_backend: str = "auto"
    # Chinese variant conversion: auto|s2t|t2s|tw|hk
    # auto = no conversion (current behavior). s2t = simplified→traditional. t2s = traditional→simplified.
    # tw = Taiwan traditional. hk = Hong Kong traditional. Requires opencc.
    chinese_variant: str = "auto"
    # Keep explanatory footnote data in translation artifacts, but do not pass
    # it to the runtime renderer by default. Runtime footnotes append a footer
    # strip to page PNGs; doing that implicitly caused page-height drift and
    # bottom text pollution in e2e manga output.
    render_footnotes: bool = False
