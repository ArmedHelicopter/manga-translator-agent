"""MGA CLI entrypoint -- Click commands for translation, benchmark, memory, and review."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import click

logger = logging.getLogger("mga.cli")


def _seed_memory(learn_dir: Path, project_dir: Path, mode: str = "auto") -> None:
    """Run the LearningEngine to extract and seed memory from *learn_dir*."""
    from mga.learning.engine import LearningEngine

    engine = LearningEngine(project_dir)
    result = engine.learn(learn_dir, mode=mode)
    click.echo(
        f"Learning complete: {len(result.characters)} characters, "
        f"{len(result.terms)} terms"
    )


def _resolve_provider(cfg, stage: str = "vision"):
    route = cfg.provider_routes.get(stage)
    name = route.primary.provider if route and route.primary.provider else "openai"
    return name, cfg.provider_settings.get(name, {})


_NOVEL_EXTENSIONS = {".epub", ".txt", ".mobi"}


def _detect_mode(input_path: str, mode: str | None) -> tuple[str, str]:
    """Detect pipeline mode and input format from file extension.

    Returns (pipeline_mode, input_format).
    """
    if mode == "novel":
        return "novel", Path(input_path).suffix.lstrip(".").lower()
    if mode == "manga":
        return "manga", "images"
    # Auto-detect: novel extensions -> novel mode
    ext = Path(input_path).suffix.lower()
    if ext in _NOVEL_EXTENSIONS:
        return "novel", ext.lstrip(".")
    return "manga", "images"


@click.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option("-o", "--output-path", required=True, type=click.Path())
@click.option("--provider", default=None)
@click.option("--format", "output_format", default=None)
@click.option("--mode", type=click.Choice(["manga", "novel"]), default=None)
@click.option("--learn-from", default=None, type=click.Path(exists=True))
@click.option("--learn-only", is_flag=True)
@click.option("--lang", default="ja-zh")
@click.option("--config", "config_path", default=None, type=click.Path(exists=True))
@click.option("--save-json", is_flag=True, help="Save full translation report and debug artifacts.")
@click.option("--bilingual", is_flag=True, help="Output bilingual PDF (original + translation side-by-side).")
@click.option("--dry-run", is_flag=True)
def translate(input_path, output_path, provider, output_format, mode, learn_from, learn_only, lang, config_path, save_json, bilingual, dry_run):
    """Run the translation pipeline on INPUT_PATH."""
    from mga.config.loader import build_project_config
    from mga.pipeline.orchestrator import PipelineOrchestrator

    parts = lang.split("-", 1)
    src, tgt = parts[0] if parts else "ja", parts[1] if len(parts) > 1 else "zh-CN"
    pipeline_mode, detected_format = _detect_mode(input_path, mode)
    cfg, _ = build_project_config(
        input_path=input_path, output_path=output_path,
        provider_override=provider, save_json=False, dry_run=dry_run, config_path=config_path,
    )
    cfg.source_lang, cfg.target_lang = src, tgt
    cfg.pipeline_mode = pipeline_mode
    cfg.save_artifacts = save_json
    if output_format:
        cfg.output_format = output_format
    elif pipeline_mode == "novel":
        cfg.output_format = detected_format
    else:
        cfg.output_format = "images"
    cfg.input_format = detected_format
    if bilingual:
        cfg.output_format = "bilingual"

    if learn_from:
        _seed_memory(Path(learn_from), Path(cfg.working_dir), mode=pipeline_mode)
        if learn_only:
            click.echo("Memory seeded. --learn-only set, skipping translation.")
            return
    if dry_run:
        click.echo(f"Dry run:\n{cfg.model_dump_json(indent=2)}")
        return

    mode_label = f" ({pipeline_mode} mode)" if pipeline_mode == "novel" else ""
    click.echo(f"Translating{mode_label} {input_path} -> {output_path}  ({src} -> {tgt})")
    ctx = PipelineOrchestrator(config=cfg).run(input_path, output_path, cfg)
    out = Path(output_path)
    if pipeline_mode == "novel":
        out.parent.mkdir(parents=True, exist_ok=True)
    else:
        out.mkdir(parents=True, exist_ok=True)
    # run.json is now written by OutputStage via ArtifactStore — no duplicate write here
    run_dir = out if pipeline_mode == "manga" else out.parent
    click.echo(f"Done. run.json -> {run_dir / 'run.json'}")
    for err in ctx.errors:
        click.echo(f"  [!] {err['stage']}: {err['error']}", err=True)


@click.group()
def legacy():
    """Legacy benchmark commands."""

@legacy.command("benchmark-extraction")
@click.argument("input_path", type=click.Path(exists=True))
@click.option("-o", "--output-path", required=True, type=click.Path())
@click.option("--config", "config_path", default=None, type=click.Path(exists=True))
def legacy_benchmark_extraction(input_path, output_path, config_path):
    from mga.artifacts import ArtifactStore
    from mga.benchmark.evaluate import run_extraction_benchmark
    from mga.config.loader import build_project_config
    from mga.format.manifest import discover_image_paths
    from mga.models import Page, PageImage
    from mga.providers import get_provider

    cfg, _ = build_project_config(
        input_path=input_path, output_path=output_path,
        provider_override=None, save_json=False, dry_run=False, config_path=config_path,
    )
    pname, settings = _resolve_provider(cfg, "vision")
    provider = get_provider(pname, **settings)
    pages = [Page(page_id=f"p{i}", page_index=i, image=PageImage(path=str(p)))
             for i, p in enumerate(discover_image_paths(Path(input_path)))]
    summary = run_extraction_benchmark(
        pages=pages, provider=provider, store=ArtifactStore(Path(output_path)),
        ocr_specs=["tesseract_jpn"],
    )
    click.echo(f"Extraction benchmark complete: {summary['page_count']} pages.")


@click.command()
@click.argument("input_path", type=click.Path(exists=True))
@click.option("-o", "--output-path", required=True, type=click.Path())
@click.option("--no-compare-with-internal", is_flag=True)
@click.option("--config", "config_path", default=None, type=click.Path(exists=True))
def benchmark_external(input_path, output_path, no_compare_with_internal, config_path):
    """Run the external (manga-image-translator) benchmark."""
    from mga.benchmark.external import run_manga_image_translator_baseline
    click.echo(f"Running external benchmark: {input_path} -> {output_path}")
    summary = run_manga_image_translator_baseline(
        repo_dir=None, input_dir=Path(input_path), output_dir=Path(output_path),
    )
    click.echo(json.dumps(summary, indent=2, ensure_ascii=False))


@click.group()
def memory():
    """Memory management commands."""

@memory.command("init")
@click.argument("project_dir", type=click.Path())
def memory_init(project_dir):
    from mga.memory.state import StateManager
    p = Path(project_dir); StateManager.load(p)
    click.echo(f"Memory initialized at {p / 'memory' / 'state'}")

@memory.command("sync")
@click.argument("project_dir", type=click.Path(exists=True))
def memory_sync(project_dir):
    from mga.memory.sync import state_to_wiki
    state_to_wiki(Path(project_dir))
    click.echo(f"Wiki synced at {Path(project_dir) / 'memory'}")


@click.group()
def profile():
    """Character profile commands."""

@profile.command("list")
@click.argument("project_dir", type=click.Path(exists=True))
def profile_list(project_dir):
    from mga.memory.state import StateManager
    chars = StateManager.list_characters(Path(project_dir))
    if not chars:
        click.echo("No character profiles found."); return
    for c in chars:
        click.echo(f"  {c.character_id}: {c.name_jp} / {c.name_zh}  ({c.archetype})")


@click.group()
def term():
    """Terminology commands."""

@term.command("list")
@click.argument("project_dir", type=click.Path(exists=True))
def term_list(project_dir):
    from mga.memory.state import StateManager
    terms = StateManager.list_terms(Path(project_dir))
    if not terms:
        click.echo("No terminology entries found."); return
    for t in terms:
        click.echo(f"  {t.term_id}: {t.term_jp} -> {t.term_zh}  (freq={t.frequency})")


@click.group()
def main():
    """Manga Translate Agent (mga) CLI."""

main.add_command(translate)
main.add_command(benchmark_external)
main.add_command(legacy)
main.add_command(memory)
main.add_command(profile)
main.add_command(term)

if __name__ == "__main__":
    main()
