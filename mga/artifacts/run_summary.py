"""Unified run summary — single source of truth for run.json."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any

from ..pipeline.stages import PipelineContext
from ..models.project import ProjectConfig


@dataclass
class RunSummary:
    """Unified run summary schema — replaces dual write in OutputStage + CLI."""
    timestamp: str = ""
    pipeline_mode: str = "manga"
    source_lang: str = ""
    target_lang: str = ""
    provider: str = ""
    input_path: str = ""
    output_path: str = ""
    input_format: str = ""
    output_format: str = ""
    page_count: int = 0
    translation_count: int = 0
    stages_completed: list[str] = field(default_factory=list)
    stage_timings: dict[str, float] = field(default_factory=dict)
    total_duration: float = 0.0
    error_count: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    status: str = "completed"


def build_run_summary(ctx: PipelineContext, cfg: ProjectConfig) -> RunSummary:
    """Build a unified RunSummary from PipelineContext and ProjectConfig."""
    # Determine status from errors
    if not ctx.errors:
        status = "completed"
    elif any(e.get("stage") == "translation" for e in ctx.errors):
        status = "failed"
    else:
        status = "partial"

    # Extract provider name from provider_routes or default
    provider = ""
    route = cfg.provider_routes.get("translation")
    if route and route.primary.provider:
        provider = route.primary.provider
    elif cfg.provider_routes.get("vision"):
        provider = cfg.provider_routes["vision"].primary.provider or ""

    return RunSummary(
        timestamp=datetime.now(timezone.utc).isoformat(),
        pipeline_mode=cfg.pipeline_mode,
        source_lang=cfg.source_lang,
        target_lang=cfg.target_lang,
        provider=provider,
        input_path=ctx.metadata.get("input_path", ""),
        output_path=ctx.metadata.get("output_path", ""),
        input_format=cfg.input_format,
        output_format=cfg.output_format,
        page_count=len(ctx.pages),
        translation_count=len(ctx.translations),
        stages_completed=list(ctx.artifacts.keys()),
        stage_timings=ctx.metadata.get("stage_timings", {}),
        total_duration=ctx.metadata.get("total_duration", 0.0),
        error_count=len(ctx.errors),
        errors=ctx.errors,
        status=status,
    )


def write_run_summary(store: Any, summary: RunSummary) -> str:
    """Write run summary to store. Returns relative path."""
    return store.write_run_summary(asdict(summary))
