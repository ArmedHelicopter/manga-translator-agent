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
    graph_mode: str = ""
    provider_routes: dict[str, dict[str, Any]] = field(default_factory=dict)
    runtime: dict[str, Any] = field(default_factory=dict)
    provider_cascade_errors: list[dict[str, Any]] = field(default_factory=list)
    provider_cascade_calls: list[dict[str, Any]] = field(default_factory=list)


def _collect_provider_cascade_errors(ctx: PipelineContext) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    for stage, artifact in ctx.artifacts.items():
        if not isinstance(artifact, dict):
            continue
        for error in artifact.get("provider_cascade_errors", []) or []:
            if isinstance(error, dict):
                errors.append({"stage": stage, **error})
    return errors


def _collect_provider_cascade_calls(ctx: PipelineContext) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for stage, artifact in ctx.artifacts.items():
        if not isinstance(artifact, dict):
            continue
        for call in artifact.get("provider_cascade_calls", []) or []:
            if isinstance(call, dict):
                calls.append({"stage": stage, **call})

        if stage != "translation":
            continue
        dialogue_realization = artifact.get("dialogue_realization", {})
        entries = (
            dialogue_realization.get("entries", [])
            if isinstance(dialogue_realization, dict)
            else []
        )
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            provider_trace = entry.get("provider", {})
            if not isinstance(provider_trace, dict):
                continue
            for trace_name in ("semantic", "persona"):
                trace = provider_trace.get(trace_name, {})
                if isinstance(trace, dict) and trace:
                    calls.append({
                        "stage": "translation",
                        "bubble_id": entry.get("bubble_id", ""),
                        **trace,
                    })
    return calls


def _collect_provider_routes(cfg: ProjectConfig) -> dict[str, dict[str, Any]]:
    routes: dict[str, dict[str, Any]] = {}
    for stage, route in cfg.provider_routes.items():
        stage_route: dict[str, Any] = {}
        for role in ("primary", "fallback", "local"):
            provider_route = getattr(route, role)
            if provider_route is None:
                continue
            payload = provider_route.model_dump(exclude_none=True)
            if payload.get("provider") or payload.get("model"):
                stage_route[role] = payload
        if stage_route:
            routes[stage] = stage_route
    return routes


def _collect_runtime_details(ctx: PipelineContext) -> dict[str, Any]:
    payload_dir = ctx.metadata.get("artifact_payload_dir", "")
    render_artifact = ctx.artifacts.get("render", {})
    runtime: dict[str, Any] = {
        "type": "external-two-pass" if payload_dir else "none",
    }
    if payload_dir:
        runtime["artifact_payload_dir"] = str(payload_dir)

    if isinstance(render_artifact, dict) and render_artifact:
        mode = render_artifact.get("mode", "")
        runtime["render_mode"] = mode
        if "output_dir" in render_artifact:
            runtime["render_output_dir"] = render_artifact["output_dir"]
        if "pages_rendered" in render_artifact:
            runtime["pages_rendered"] = render_artifact["pages_rendered"]
        if "rendered_images" in render_artifact:
            runtime["rendered_images"] = render_artifact["rendered_images"]
        if "error" in render_artifact:
            runtime["render_error"] = render_artifact["error"]
        if mode == "skipped" and not payload_dir:
            runtime["type"] = "artifact-only"

    return runtime


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

    dialogue_realization = ctx.artifacts.get("translation", {}).get("dialogue_realization", {})
    graph_mode = "translation_graph_v0_linear" if dialogue_realization else ""

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
        graph_mode=graph_mode,
        provider_routes=_collect_provider_routes(cfg),
        runtime=_collect_runtime_details(ctx),
        provider_cascade_errors=_collect_provider_cascade_errors(ctx),
        provider_cascade_calls=_collect_provider_cascade_calls(ctx),
    )


def write_run_summary(store: Any, summary: RunSummary) -> str:
    """Write run summary to store. Returns relative path."""
    return store.write_run_summary(asdict(summary))
