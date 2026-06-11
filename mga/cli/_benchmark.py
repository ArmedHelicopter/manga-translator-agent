"""Benchmark commands for CLI."""

from __future__ import annotations

from pathlib import Path

import click


@click.group(name="benchmark")
def benchmark_group():
    """Benchmark external runtime and translation quality."""
    pass


@benchmark_group.command("external")
@click.argument("input_path", type=click.Path(path_type=Path))
@click.argument("output_path", type=click.Path(path_type=Path))
@click.option("--provider", help="Override translation provider")
@click.option("--metrics", multiple=True, default=["accuracy", "speed", "coherence"],
              help="Metrics to evaluate")
@click.option("--report", type=click.Path(path_type=Path), help="Output report path")
def benchmark_external(input_path: Path, output_path: Path, provider: str | None,
                       metrics: tuple[str, ...], report: Path | None):
    """Run external runtime benchmark with quality evaluation."""
    from mga.benchmark.external import run_external_benchmark

    result = run_external_benchmark(
        input_path=input_path,
        output_path=output_path,
        provider=provider,
        metrics=list(metrics),
    )

    click.echo(f"Benchmark complete: {result.summary}")
    if report:
        import json
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        click.echo(f"Report: {report}")


@benchmark_group.command("compare")
@click.argument("baseline_dir", type=click.Path(path_type=Path))
@click.argument("candidate_dir", type=click.Path(path_type=Path))
@click.option("--metric", default="all", help="Specific metric to compare")
def benchmark_compare(baseline_dir: Path, candidate_dir: Path, metric: str):
    """Compare two benchmark runs."""
    from mga.benchmark.evaluate import compare_benchmarks

    result = compare_benchmarks(baseline_dir, candidate_dir, metric=metric if metric != "all" else None)

    click.echo(f"Comparison: baseline={result.baseline_score:.2f}, candidate={result.candidate_score:.2f}")
    if result.delta > 0:
        click.echo(f"  ↑ {result.delta:.2%} improvement", err=False)
    elif result.delta < 0:
        click.echo(f"  ↓ {abs(result.delta):.2%} regression", err=True)
    else:
        click.echo("  ≈ no change")


@benchmark_group.command("list")
@click.argument("results_dir", type=click.Path(path_type=Path))
def benchmark_list(results_dir: Path):
    """List available benchmark results."""
    if not results_dir.exists():
        click.echo("No benchmark results found")
        return

    for result_file in sorted(results_dir.glob("run-*.json")):
        import json
        data = json.loads(result_file.read_text(encoding="utf-8"))
        timestamp = data.get("timestamp", "unknown")
        score = data.get("score", "N/A")
        click.echo(f"  {result_file.stem}: {timestamp} [{score}]")


@benchmark_group.command("export")
@click.argument("results_dir", type=click.Path(path_type=Path))
@click.argument("output_format", type=click.Choice(["csv", "json", "markdown"]))
@click.argument("output_file", type=click.Path(path_type=Path))
def benchmark_export(results_dir: Path, output_format: str, output_file: Path):
    """Export benchmark results to file."""
    import json

    results = []
    for result_file in sorted(results_dir.glob("run-*.json")):
        data = json.loads(result_file.read_text(encoding="utf-8"))
        results.append(data)

    output_file.parent.mkdir(parents=True, exist_ok=True)

    if output_format == "json":
        output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    elif output_format == "csv":
        import csv
        with output_file.open("w", newline="", encoding="utf-8") as f:
            if results:
                writer = csv.DictWriter(f, fieldnames=results[0].keys())
                writer.writeheader()
                writer.writerows(results)
    else:  # markdown
        lines = ["# Benchmark Results", "", "| Timestamp | Score | Provider |", "|---|---|---|"]
        for r in results:
            lines.append(f"| {r.get('timestamp', '')} | {r.get('score', '')} | {r.get('provider', '')} |")
        output_file.write_text("\n".join(lines), encoding="utf-8")

    click.echo(f"Exported {len(results)} results: {output_file}")


# Legacy commands
_legacy_group = click.Group(name="legacy")


@_legacy_group.command("benchmark-extraction")
@click.argument("input_path", type=click.Path(path_type=Path))
@click.argument("output_path", type=click.Path(path_type=Path))
@click.option("--force", is_flag=True, help="Force overwrite existing output")
def legacy_benchmark_extraction(input_path: Path, output_path: Path, force: bool):
    """Legacy: extract text from images for benchmark comparison."""
    click.echo("Deprecated: Use `manga-translate benchmark extract` instead")
    from mga.benchmark.external import extract_text_for_benchmark

    result = extract_text_for_benchmark(input_path, output_path, force=force)
    click.echo(f"Extracted {result.page_count} pages, {result.bubble_count} bubbles: {output_path}")