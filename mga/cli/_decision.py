"""Decision memory CLI commands."""

from __future__ import annotations

from pathlib import Path

import click

from mga.memory.entities import DecisionState
from mga.memory.state import StateManager


@click.group(name="decision")
def decision_group():
    """Translation decision commands."""
    pass


@decision_group.command(name="list")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path), default=Path("."))
def decision_list(project_dir: Path):
    """List recorded translation decisions."""
    decisions = StateManager.list_decisions(project_dir)
    if not decisions:
        click.echo("No translation decisions found.")
        return
    for d in decisions:
        click.echo(f"  {d.decision_id}: [{d.stage}] {d.decision} (confidence={d.confidence})")


@decision_group.command(name="add")
@click.argument("project_dir", type=click.Path(path_type=Path), default=Path("."))
@click.option("--decision-id", "decision_id", default=None)
@click.option("--stage", required=True)
@click.option("--input-ref", "input_ref", default="")
@click.option("--decision", "decision_text", required=True)
@click.option("--rationale", default="")
@click.option("--confidence", type=float, default=0.0, show_default=True)
def decision_add(
    project_dir: Path,
    decision_id: str | None,
    stage: str,
    input_ref: str,
    decision_text: str,
    rationale: str,
    confidence: float,
):
    """Record a translation decision in memory state."""
    decision_state = DecisionState(
        decision_id=decision_id or "",
        stage=stage,
        input_ref=input_ref,
        decision=decision_text,
        rationale=rationale,
        confidence=confidence,
    )
    StateManager.upsert_decision(project_dir, decision_state)
    click.echo(f"Decision saved: {decision_state.decision_id}")