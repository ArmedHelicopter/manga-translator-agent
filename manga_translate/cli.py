"""Compatibility CLI shim.

This module provides the CLI entrypoint that existing tests import from
``manga_translate.cli``. It re-exports a Click group that delegates to
the mga CLI implementation.

The key design constraint: functions are looked up from THIS module's
namespace at call time (not imported at top level in mga code) so that
monkeypatching at the ``manga_translate.cli.*`` path works correctly.
"""

from __future__ import annotations

import json
from pathlib import Path

import click

from mga.artifacts import ArtifactStore
from mga.config.loader import build_project_config


def run_external_translation_runtime(**kwargs):
    from mga.runtime_bridge.external import run_external_translation_runtime as _impl
    return _impl(**kwargs)


def run_manga_image_translator_baseline(**kwargs):
    from mga.benchmark.external import run_manga_image_translator_baseline as _impl
    return _impl(**kwargs)


def run_extraction_benchmark(**kwargs):
    from mga.benchmark.evaluate import run_extraction_benchmark as _impl
    return _impl(**kwargs)


def run_translation_benchmark(**kwargs):
    from mga.benchmark.evaluate import run_translation_benchmark as _impl
    return _impl(**kwargs)


def run_external_translation_benchmark(**kwargs):
    from mga.benchmark.evaluate import run_external_translation_benchmark as _impl
    return _impl(**kwargs)


def build_legacy_provider(raw_config, primary_provider):
    return primary_provider


def ingest_pages(project_config, store):
    from mga.format.manifest import discover_image_paths, load_image_metadata
    from mga.models import Page, PageImage

    input_dir = Path(project_config.working_dir)
    pages = []
    for idx, image_path in enumerate(discover_image_paths(input_dir)):
        width, height, dpi = load_image_metadata(image_path)
        pages.append(
            Page(
                page_id=f"page-{idx + 1:04d}",
                page_index=idx,
                image=PageImage(
                    path=str(Path(image_path).resolve()),
                    width=width,
                    height=height,
                    dpi=dpi,
                ),
                source_lang=getattr(project_config, "source_lang", "ja"),
            )
        )
    return pages, None


@click.group()
def main():
    """Manga Translate Agent CLI."""


@main.command()
@click.argument("input_path")
@click.option("-o", "--output-path", required=True, help="Output directory.")
@click.option("--provider", default=None, help="Provider override.")
@click.option("--save-json", is_flag=True, help="Save debug JSON.")
@click.option("--dry-run", is_flag=True, help="Dry run (not supported for translate).")
@click.option("--verbose", is_flag=True, help="Verbose output.")
def translate(input_path, output_path, provider, save_json, dry_run, verbose):
    """Translate manga images using the external runtime."""
    if dry_run:
        raise click.BadParameter("translate does not support '--dry-run'")

    project_config, raw_config = build_project_config(
        input_path=input_path,
        output_path=output_path,
        provider_override=provider,
        save_json=save_json,
        dry_run=dry_run,
    )

    store = ArtifactStore(Path(project_config.output_dir))
    result = run_external_translation_runtime(
        project_config=project_config,
        raw_config=raw_config,
        store=store,
    )

    summary = result["summary"]
    manifest = result.get("manifest")

    run_payload = {
        "project_name": project_config.project_name,
        "translation_mode": "external-core",
        "runtime": {
            "type": "external-core",
            "repo_dir": summary.get("repo_dir", ""),
        },
        "status": "completed",
        "input_dir": project_config.working_dir,
        "output_dir": project_config.output_dir,
    }
    if manifest is not None:
        run_payload["manifest"] = manifest

    output_dir = Path(project_config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "run.json").write_text(
        json.dumps(run_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest if manifest is not None else {}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    click.echo(f"Translation completed. Output: {output_dir}")


@main.command()
@click.argument("input_path")
@click.option("-o", "--output-path", required=True, help="Output directory.")
@click.option("--no-compare-with-internal", is_flag=True, help="Skip internal comparison.")
@click.option("--verbose", is_flag=True, help="Verbose output.")
def benchmark_external(input_path, output_path, no_compare_with_internal, verbose):
    """Run external benchmark against manga-image-translator."""
    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    run_payload = {
        "status": "completed",
        "compare_with_internal": not no_compare_with_internal,
    }

    try:
        external_summary = run_manga_image_translator_baseline(
            repo_dir=None,
            input_dir=Path(input_path),
            output_dir=output_dir,
        )

        run_payload["parsed_page_count"] = external_summary.get("parsed_page_count", 0)
        run_payload["external_translation_report"] = "benchmark/external-translation-report.json"

        if not no_compare_with_internal:
            project_config, raw_config = build_project_config(
                input_path=input_path,
                output_path=output_path,
                provider_override=None,
                save_json=False,
                dry_run=False,
            )

            pages, _ = ingest_pages(project_config, ArtifactStore(output_dir))

            if pages:
                internal_report = run_translation_benchmark(
                    pages=pages,
                    provider=build_legacy_provider(raw_config, None),
                    store=ArtifactStore(output_dir),
                    vision_modes=["structured", "direct"],
                )
                normalized_path = output_dir / "external-baseline-text-normalized.json"
                external_pages = []
                if normalized_path.exists():
                    external_pages = json.loads(normalized_path.read_text(encoding="utf-8"))

                run_external_translation_benchmark(
                    pages=pages,
                    internal_translation_report=internal_report,
                    external_pages=external_pages,
                    store=ArtifactStore(output_dir),
                )

    except Exception as exc:
        run_payload["status"] = "failed"
        run_payload["error"] = str(exc)

    benchmark_dir = output_dir / "benchmark"
    benchmark_dir.mkdir(parents=True, exist_ok=True)
    (benchmark_dir / "run.json").write_text(
        json.dumps(run_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if run_payload["status"] == "failed":
        raise RuntimeError(run_payload["error"])

    click.echo(f"Benchmark completed. Output: {benchmark_dir}")


@main.group()
def legacy():
    """Legacy and research commands."""
    pass


@legacy.command("benchmark-extraction")
@click.argument("input_path")
@click.option("-o", "--output-path", required=True, help="Output directory.")
@click.option("--verbose", is_flag=True, help="Verbose output.")
def benchmark_extraction(input_path, output_path, verbose):
    """Run extraction benchmark."""
    output_dir = Path(output_path)
    benchmark_dir = output_dir / "benchmark"
    benchmark_dir.mkdir(parents=True, exist_ok=True)

    run_payload = {
        "status": "completed",
    }

    try:
        project_config, raw_config = build_project_config(
            input_path=input_path,
            output_path=output_path,
            provider_override=None,
            save_json=False,
            dry_run=False,
        )

        store = ArtifactStore(output_dir)
        pages, _ = ingest_pages(project_config, store)

        provider = build_legacy_provider(raw_config, raw_config.get("providers", {}).get("openai", {}))

        run_extraction_benchmark(
            pages=pages,
            provider=provider,
            store=store,
        )

    except Exception as exc:
        run_payload["status"] = "failed"
        run_payload["error"] = str(exc)

    (benchmark_dir / "run.json").write_text(
        json.dumps(run_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if run_payload["status"] == "failed":
        raise RuntimeError(run_payload["error"])

    click.echo(f"Extraction benchmark completed. Output: {benchmark_dir}")
