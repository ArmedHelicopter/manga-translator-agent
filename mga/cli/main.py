"""MGA CLI entrypoint -- Click commands for translation, benchmark, memory, and review.

This module is intentionally small (~250 lines). Complex logic is delegated to
submodules: _provider.py, _memory.py, _benchmark.py, _graph.py, _review.py, _batch.py.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import click

logger = logging.getLogger("mga.cli")

# ---------------------------------------------------------------------------
# Submodule imports (delegation pattern)
# ---------------------------------------------------------------------------
from ._scene import scene_group as scene_group_cmd
from ._decision import decision_group
from ._graph import graph_group
from ._review import review_group
from ._batch import batch_group
from ._provider import (
    check_provider_connectivity,
    check_vision_capability,
    resolve_learning_provider,
    resolve_stage_provider,
)
from ._provider import (
    resolve_stage_provider as _resolve_stage_provider,
    check_vision_capability as _check_vision_provider_capability,
)
from ._memory import memory_group
from ._benchmark import benchmark_group, _legacy_group
from ._distill import distill_group
from ._profile import profile
from ._term import term
from ._term import term_group

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _detect_mode(input_path: str, mode: str | None) -> tuple[str, str]:
    """Detect pipeline mode and input format from file extension."""
    novel_exts = {".epub", ".txt", ".mobi"}
    manga_exts = {".pdf", ".epub", ".cbz", ".cbr", ".mobi"}
    auto_manga_exts = {".pdf", ".cbz", ".cbr"}

    if mode == "novel":
        return "novel", Path(input_path).suffix.lstrip(".").lower()
    if mode == "manga":
        ext = Path(input_path).suffix.lower()
        if ext in manga_exts:
            return "manga", ext.lstrip(".")
        return "manga", "images"

    ext = Path(input_path).suffix.lower()
    if ext in novel_exts:
        return "novel", ext.lstrip(".")
    if ext in auto_manga_exts:
        return "manga", ext.lstrip(".")
    return "manga", "images"


def _seed_memory(learn_dir: Path, project_dir: Path, mode: str = "auto", provider=None):
    """Run LearningEngine to extract and seed memory."""
    from mga.learning.engine import LearningEngine

    engine = LearningEngine(project_dir, provider=provider)
    result = engine.learn(learn_dir, mode=mode)
    click.echo(f"Learning: {len(result.characters)} chars, {len(result.terms)} terms")


def _export_profiles(project_dir: Path, output_profiles: Path) -> int:
    """Copy learned profile TOML files to output directory."""
    import shutil

    source_dir = project_dir / "character_profiles"
    output_profiles.mkdir(parents=True, exist_ok=True)
    count = 0
    for src in sorted(source_dir.rglob("*.toml")) if source_dir.exists() else []:
        dst = output_profiles / src.relative_to(source_dir)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        count += 1
    return count


def _parse_kv(values: tuple[str, ...], name: str) -> dict[str, str]:
    """Parse key=value pairs."""
    result = {}
    for v in values:
        if "=" not in v:
            raise click.ClickException(f"{name} must use key=value: {v}")
        k, val = v.split("=", 1)
        if not (k := k.strip()):
            raise click.ClickException(f"{name} key cannot be empty: {v}")
        result[k] = val.strip()
    return result


# ---------------------------------------------------------------------------
# Translate command (main entry point)
# ---------------------------------------------------------------------------

@click.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option("-o", "--output-path", required=True, type=click.Path())
@click.option("--provider", help="Override provider")
@click.option("--format", "output_format", help="Output format")
@click.option("--mode", type=click.Choice(["manga", "novel"]))
@click.option("--learn-from", type=click.Path(exists=True), help="Learn from existing translations")
@click.option("--learn-only", is_flag=True, help="Learn only, skip translation")
@click.option("--output-profiles", type=click.Path(), help="Export profiles to directory")
@click.option("--lang", default="ja-zh", help="Source-target language pair")
@click.option("--config", "config_path", type=click.Path(exists=True))
@click.option("--save-json", is_flag=True, help="Save full translation report")
@click.option("--bilingual", is_flag=True, help="Output bilingual PDF")
@click.option("--incremental", is_flag=True, help="Use incremental translation")
@click.option("--chapter-id", default="", help="Chapter ID for incremental")
@click.option("--dry-run", is_flag=True, help="Show config and exit")
@click.option("-v", "--verbose", is_flag=True)
@click.option("--artifact-payload-dir", type=click.Path(exists=True), help="Reuse existing payload")
@click.option("--parallel-mode", type=click.Choice(["serial", "parallel", "pipelined", "semantic-parallel", "batch-parallel"]))
@click.option("--concurrency", type=int, help="Max pages in flight")
@click.option("--auto-vision-model", is_flag=True, help="Auto-switch vision model if rejected")
@click.option("--inpaint-backend", type=click.Choice(["auto", "none", "lama_large", "lama_mpe", "sd", "original", "default"]), default="auto", help="Inpainter backend for manga-image-translator runtime")
@click.option("--chinese-variant", type=click.Choice(["auto", "s2t", "t2s", "tw", "hk"]), default="auto", help="Convert Chinese variant in rendered output (requires opencc)")
def translate(
    input_path, output_path, provider, output_format, mode,
    learn_from, learn_only, output_profiles, lang, config_path,
    save_json, bilingual, incremental, chapter_id, dry_run, verbose,
    artifact_payload_dir, parallel_mode, concurrency, auto_vision_model,
    inpaint_backend, chinese_variant,
):
    """Run translation pipeline on INPUT_PATH."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
        logging.getLogger("mga").setLevel(logging.DEBUG)

    src, tgt = lang.split("-", 1) if "-" in lang else ("ja", "zh-CN")
    pipeline_mode, detected_format = _detect_mode(input_path, mode)

    from mga.config.loader import build_project_config
    from mga.pipeline.orchestrator import PipelineOrchestrator

    cfg, _ = build_project_config(
        input_path=input_path, output_path=output_path,
        provider_override=provider, save_json=False, dry_run=dry_run, config_path=config_path,
    )
    cfg.source_lang, cfg.target_lang = src, tgt
    cfg.pipeline_mode = pipeline_mode
    cfg.save_artifacts = save_json

    if inpaint_backend and inpaint_backend != "auto":
        cfg.inpaint_backend = inpaint_backend
    if chinese_variant and chinese_variant != "auto":
        cfg.chinese_variant = chinese_variant

    if parallel_mode:
        cfg.parallel_mode = parallel_mode
        cfg.translation_config["parallel_mode"] = parallel_mode
    if concurrency is not None:
        cfg.pipeline_concurrency = concurrency
        cfg.translation_max_workers = concurrency
        if cfg.translation_config.get("parallel_mode") == "batch-parallel":
            cfg.translation_config["batch_size"] = concurrency
            cfg.translation_config.setdefault("max_concurrent_requests", concurrency)
        else:
            cfg.translation_config["max_concurrent_requests"] = concurrency
    if output_format:
        cfg.output_format = output_format
    elif pipeline_mode == "novel":
        cfg.output_format = detected_format
    else:
        cfg.output_format = "images"
    cfg.input_format = detected_format
    if bilingual:
        cfg.output_format = "bilingual"

    # Learning phase
    effective_learn = learn_from or (input_path if learn_only else None)
    if effective_learn:
        _seed_memory(Path(effective_learn), Path(cfg.working_dir), mode=pipeline_mode,
                     provider=resolve_learning_provider(cfg))
        if output_profiles:
            count = _export_profiles(Path(cfg.working_dir), Path(output_profiles))
            click.echo(f"Profiles exported: {count}")
        if learn_only:
            click.echo("Memory seeded. --learn-only set, skipping translation.")
            return

    if dry_run:
        click.echo(f"Dry run:\n{cfg.model_dump_json(indent=2)}")
        return

    mode_label = f" ({pipeline_mode} mode)" if pipeline_mode == "novel" else ""
    click.echo(f"Translating{mode_label} {input_path} -> {output_path}  ({src} -> {tgt})")

    pipeline_metadata: dict = {}
    if pipeline_mode == "manga":
        click.echo("Provider pre-check...")
        check_provider_connectivity(cfg)
        click.echo("Vision pre-check...")
        check_vision_capability(cfg, auto_vision_model=auto_vision_model)
        click.echo("Pre-checks OK")

        from mga.memory.service import get_memory_service
        from mga.cultural.service import get_cultural_service
        pipeline_metadata["memory_service"] = get_memory_service(cfg.working_dir)
        pipeline_metadata["cultural_service"] = get_cultural_service(cfg.working_dir)

        if artifact_payload_dir:
            payload_dir = Path(artifact_payload_dir).resolve()
            pipeline_metadata["artifact_payload_dir"] = str(payload_dir)
            click.echo(f"Pass 1 skipped. Reusing: {payload_dir}")
        else:
            try:
                from mga.runtime_bridge.external import run_export_artifact
                payload_dir = Path(output_path) / ".mga-payload"
                click.echo(f"Pass 1: Exporting to {payload_dir}")
                run_export_artifact(input_dir=Path(input_path), payload_dir=payload_dir)
                pipeline_metadata["artifact_payload_dir"] = str(payload_dir)
                click.echo("Pass 1 complete. Running pipeline...")
            except Exception as e:
                click.echo(f"Runtime export unavailable ({e}), falling back.", err=True)

    if incremental or pipeline_mode == "manga":
        from mga.pipeline.incremental import IncrementalTranslator
        ch_id = chapter_id or Path(input_path).stem or Path(input_path).name
        # Set runtime type for run.json before passing metadata
        if "artifact_payload_dir" in pipeline_metadata and "type" not in pipeline_metadata:
            pipeline_metadata["type"] = "external-two-pass"
        ctx = IncrementalTranslator(Path(cfg.working_dir), config=cfg).translate_chapter(
            input_path, output_path, ch_id, metadata=pipeline_metadata)
        click.echo(f"Incremental complete: {ch_id}")
    else:
        ctx = PipelineOrchestrator(config=cfg).run(input_path, output_path, cfg, metadata=pipeline_metadata)

    out = Path(output_path)
    (out if pipeline_mode == "manga" else out.parent).mkdir(parents=True, exist_ok=True)
    run_dir = out if pipeline_mode == "manga" else out.parent
    click.echo(f"Done. run.json -> {run_dir / 'run.json'}")

    for err in ctx.errors:
        click.echo(f"  [!] {err['stage']}: {err['error']}", err=True)
    if ctx.errors:
        first = ctx.errors[0]
        raise click.ClickException(f"Aborted at '{first['stage']}': {first['error']}")


# ---------------------------------------------------------------------------
# Memory/Profile/Term subcommands (delegated to _memory.py)
# ---------------------------------------------------------------------------
memory = memory_group  # alias for CLI group


# ---------------------------------------------------------------------------
# Benchmark subcommands (delegated to _benchmark.py)
# ---------------------------------------------------------------------------
benchmark = benchmark_group
benchmark.add_command(_legacy_group, name="legacy")


# ---------------------------------------------------------------------------
# Web/MCP servers (simple inline commands)
# ---------------------------------------------------------------------------

@click.command("web")
@click.option("--project-root", default=".", type=click.Path())
@click.option("--host", default="127.0.0.1")
@click.option("--port", default=8000, type=int)
def web(project_root, host, port):
    """Run FastAPI project management Web UI with blue-white theme."""
    from mga.web import run_web_server
    run_web_server(project_root=Path(project_root), host=host, port=port)


@click.command("mcp")
@click.option("--project-root", default=".", type=click.Path())
def mcp(project_root):
    """Run stdio MCP server."""
    from mga.mcp_server import MangaTranslatorMCPServer, run_stdio
    run_stdio(MangaTranslatorMCPServer(project_root=Path(project_root)))


# ---------------------------------------------------------------------------
# Main group
# ---------------------------------------------------------------------------

@click.group()
def main():
    """Manga Translate Agent (mga) CLI."""

main.add_command(translate)
main.add_command(benchmark)
main.add_command(memory)
main.add_command(profile)
main.add_command(term)
main.add_command(graph_group)
main.add_command(batch_group)
main.add_command(review_group)
main.add_command(scene_group_cmd)
main.add_command(decision_group)
main.add_command(distill_group)
main.add_command(web)
main.add_command(mcp)

if __name__ == "__main__":
    main()
