"""Batch processing CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import click

from mga.pipeline.batch import BatchProcessor


@click.group(name="batch")
def batch_group():
    """Batch translation commands."""
    pass


def _load_chapter_manifest(chapters_json: Path) -> list[dict[str, str]]:
    chapters_payload = json.loads(chapters_json.read_text(encoding="utf-8"))
    if not isinstance(chapters_payload, list):
        raise click.ClickException("chapters_json must contain a JSON list")
    for index, chapter in enumerate(chapters_payload):
        if not isinstance(chapter, dict):
            raise click.ClickException(f"chapter entry {index} must be an object")
        if "input_path" not in chapter or "output_path" not in chapter:
            raise click.ClickException(
                f"chapter entry {index} must include input_path and output_path"
            )
    return chapters_payload


@batch_group.command(name="run")
@click.argument("chapters_json", type=click.Path(exists=True, path_type=Path))
@click.option("--project-dir", "project_dir", required=True, type=click.Path(path_type=Path))
@click.option("--max-workers", default=1, type=int, show_default=True)
@click.option("--resume/--no-resume", default=True, show_default=True)
@click.option("--provider", default=None)
@click.option("--config", "config_path", default=None, type=click.Path(exists=True))
@click.option("--save-json", is_flag=True)
def batch_run(
    chapters_json: Path,
    project_dir: Path,
    max_workers: int,
    resume: bool,
    provider: str | None,
    config_path: Path | None,
    save_json: bool,
):
    """Run batch translation from a JSON chapter manifest."""
    chapters_payload = _load_chapter_manifest(chapters_json)
    project_dir.mkdir(parents=True, exist_ok=True)
    summary = BatchProcessor(
        project_dir,
        max_workers=max_workers,
        provider_override=provider,
        config_path=config_path,
        save_json=save_json,
    ).process(chapters_payload, resume=resume)
    summary_path = project_dir / "batch-summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    click.echo(
        "Batch complete: "
        f"{summary.get('completed', 0)} completed, "
        f"{summary.get('partial', 0)} partial, "
        f"{summary.get('failed', 0)} failed. "
        f"{summary_path}"
    )


@batch_group.command(name="status")
@click.argument("chapters_json", type=click.Path(exists=True, path_type=Path))
@click.option("--project-dir", "project_dir", required=True, type=click.Path(path_type=Path))
def batch_status(chapters_json: Path, project_dir: Path):
    """Report batch progress for a JSON chapter manifest."""
    chapters_payload = _load_chapter_manifest(chapters_json)
    project_dir.mkdir(parents=True, exist_ok=True)
    status = BatchProcessor(project_dir).get_status(chapters_payload)
    status_path = project_dir / "batch-status.json"
    status_path.write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    click.echo(
        "Batch status: "
        f"{status.get('completed', 0)} completed, "
        f"{status.get('partial', 0)} partial, "
        f"{status.get('failed', 0)} failed, "
        f"{status.get('pending', 0)} pending. "
        f"{status_path}"
    )


@batch_group.command(name="reset")
@click.option("--project-dir", "project_dir", required=True, type=click.Path(path_type=Path))
def batch_reset(project_dir: Path):
    """Clear saved batch progress."""
    BatchProcessor(project_dir).reset()
    click.echo(f"Batch progress reset: {project_dir / 'batch_progress.json'}")