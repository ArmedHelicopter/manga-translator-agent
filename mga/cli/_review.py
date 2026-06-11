"""Review CLI commands for diff, report, repair-plan, and decide."""

from __future__ import annotations

import json
from pathlib import Path

import click

from mga.artifacts import ArtifactStore
from mga.memory.entities import DecisionState
from mga.memory.state import StateManager


@click.group(name="review")
def review_group():
    """Review and diff translation artifacts."""
    pass


@review_group.command(name="diff")
@click.argument("original_json", type=click.Path(exists=True, path_type=Path))
@click.argument("revised_json", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output-path", required=True, type=click.Path(path_type=Path))
def review_diff(original_json: Path, revised_json: Path, output_path: Path):
    """Compare two translation JSON artifacts."""
    from mga.review import write_translation_diff

    artifact_path, payload = write_translation_diff(
        original_json,
        revised_json,
        output_path,
    )
    click.echo(
        "Review diff complete: "
        f"{payload['changed_bubbles']}/{payload['total_bubbles']} bubbles changed. "
        f"{artifact_path}"
    )


@review_group.command(name="report")
@click.argument("translation_report_json", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output-path", required=True, type=click.Path(path_type=Path))
def review_report(translation_report_json: Path, output_path: Path):
    """Generate review/report.json from a translation-report.json artifact."""
    from mga.review import (
        load_review_reports_from_translation_report,
        write_review_artifacts,
    )

    reports = load_review_reports_from_translation_report(translation_report_json)
    artifact_path = write_review_artifacts(ArtifactStore(output_path), reports)
    needing_review = sum(1 for report in reports if report.needs_human_review)
    click.echo(
        "Review report complete: "
        f"{len(reports)} pages, {needing_review} need review. "
        f"{artifact_path}"
    )


@review_group.command(name="repair-plan")
@click.argument("translation_report_json", type=click.Path(exists=True, path_type=Path))
@click.option("-o", "--output-path", required=True, type=click.Path(path_type=Path))
def review_repair_plan(translation_report_json: Path, output_path: Path):
    """Generate review/repair-plan.json from a translation-report.json artifact."""
    from mga.review import (
        load_repair_plan_from_translation_report,
        write_repair_plan_artifact,
    )

    payload = load_repair_plan_from_translation_report(translation_report_json)
    artifact_path = write_repair_plan_artifact(
        ArtifactStore(output_path),
        payload,
    )
    click.echo(
        "Review repair plan complete: "
        f"{payload['summary']['total_repairs']} repairs. "
        f"{artifact_path}"
    )


@review_group.command(name="decide")
@click.argument("repair_plan_json", type=click.Path(exists=True, path_type=Path))
@click.option("--project-dir", "project_dir", required=True, type=click.Path(path_type=Path))
@click.option("--bubble-id", "bubble_id", required=True)
@click.option("--status", required=True, type=click.Choice(["accept", "reject"]))
@click.option("--rationale", default="")
def review_decide(
    repair_plan_json: Path,
    project_dir: Path,
    bubble_id: str,
    status: str,
    rationale: str,
):
    """Record a human review decision for a repair-plan item."""
    payload = json.loads(repair_plan_json.read_text(encoding="utf-8"))
    repairs = payload.get("repairs", []) if isinstance(payload, dict) else []
    if not isinstance(repairs, list):
        raise click.ClickException("repair plan must contain a repairs list")

    repair = next(
        (
            item for item in repairs
            if isinstance(item, dict) and str(item.get("bubble_id", "")) == bubble_id
        ),
        None,
    )
    if repair is None:
        raise click.ClickException(f"No repair found for bubble_id={bubble_id}")

    page_id = str(repair.get("page_id") or "unknown")
    action = str(repair.get("action") or repair.get("target") or "repair")
    decision_id = f"review-{page_id}-{bubble_id}-{status}"
    try:
        confidence = float(repair.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    decision_state = DecisionState(
        decision_id=decision_id,
        stage="review",
        input_ref=f"{page_id}/{bubble_id}",
        decision=f"{status} {action} for {bubble_id}",
        rationale=rationale,
        confidence=confidence,
    )
    StateManager.upsert_decision(project_dir, decision_state)
    click.echo(f"Review decision saved: {decision_id}")