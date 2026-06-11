"""Terminology commands for CLI."""

from __future__ import annotations

from pathlib import Path

import click


@click.group(name="term")
def term_group():
    """Terminology management commands."""
    pass


@term_group.command("list")
@click.argument("project_dir", required=False, type=click.Path(exists=True, path_type=Path), default=Path("."))
def term_list(project_dir: Path):
    """List all terminology entries."""
    from mga.memory.state import StateManager

    terms = StateManager.list_terms(project_dir)
    if not terms:
        click.echo("No terms found.")
        return
    for term in terms:
        click.echo(f"{term.term_id}: {term.term_jp} -> {term.term_zh}")


@term_group.command("edit")
@click.argument("project_dir", required=False, type=click.Path(path_type=Path), default=Path("."))
@click.argument("term_id")
@click.option("--term-jp", default=None)
@click.option("--term-zh", default=None)
@click.option("--context", default=None)
@click.option("--cultural-weight", "cultural_weight", default=None)
@click.option("--strategy", default=None)
@click.option("--frequency", type=int, default=None)
@click.option("--grade", default=None, type=click.Choice(["G1", "G2", "G3", "G4", "G5", "G6", "G7"]))
@click.option("--status", default=None, type=click.Choice(["pending", "confirmed", "rejected"]))
def term_edit(
    project_dir: Path,
    term_id: str,
    term_jp: str | None,
    term_zh: str | None,
    context: str | None,
    cultural_weight: str | None,
    strategy: str | None,
    frequency: int | None,
    grade: str | None,
    status: str | None,
):
    """Create or update a terminology entry."""
    from mga.memory.entities import TermState
    from mga.memory.state import StateManager

    term = StateManager.get_term(project_dir, term_id) or TermState(term_id=term_id)
    if term_jp is not None:
        term.term_jp = term_jp
    if term_zh is not None:
        term.term_zh = term_zh
    if context is not None:
        term.context = context
    if cultural_weight is not None:
        term.cultural_weight = cultural_weight
    if strategy is not None:
        term.strategy = strategy
    if frequency is not None:
        term.frequency = frequency
    if grade is not None:
        term.grade = grade
    if status is not None:
        term.status = status

    StateManager.upsert_term(project_dir, term)
    click.echo(f"Term saved: {term_id}")


@term_group.command("import")
@click.argument("project_dir", required=False, type=click.Path(path_type=Path), default=Path("."))
@click.argument("input_file", required=False, type=click.Path(exists=True, path_type=Path), default=None)
def term_import(project_dir: Path, input_file: Path | None):
    """Import terms from TOML file, or auto-load terminology/terms.toml from project directory."""
    import json

    from mga.memory.entities import TermState
    from mga.memory.state import StateManager

    if input_file is None:
        input_file = project_dir / "terminology" / "terms.toml"
        if not input_file.exists():
            click.echo(f"No terminology/terms.toml found in {project_dir}")
            return

    if input_file.suffix == ".toml":
        import tomllib
        data = tomllib.loads(input_file.read_text(encoding="utf-8"))
        # Support both [terms] table and list format
        terms_data = data.get("terms", data if isinstance(data, list) else [])
    else:
        data = json.loads(input_file.read_text(encoding="utf-8"))
        terms_data = data if isinstance(data, list) else data.get("terms", [])
    count = 0
    if isinstance(terms_data, dict):
        for term_id, entry in terms_data.items():
            if isinstance(entry, dict):
                entry = {**entry, "term_id": term_id}
                # Normalize field names from TOML format
                if "term_target" in entry:
                    entry["term_zh"] = entry.pop("term_target")
                if "notes" in entry:
                    entry["context"] = entry.pop("notes")
                if "problem_types" in entry and "cultural_weight" not in entry:
                    pts = entry.pop("problem_types")
                    entry["cultural_weight"] = pts[0] if isinstance(pts, list) and pts else str(pts)
            term = TermState(**entry)
            StateManager.upsert_term(project_dir, term)
            count += 1
    else:
        for entry in terms_data:
            if "term_target" in entry:
                entry["term_zh"] = entry.pop("term_target")
            if "notes" in entry:
                entry["context"] = entry.pop("notes")
            if "problem_types" in entry and "cultural_weight" not in entry:
                pts = entry.pop("problem_types")
                entry["cultural_weight"] = pts[0] if isinstance(pts, list) and pts else str(pts)
            term = TermState(**entry)
            StateManager.upsert_term(project_dir, term)
            count += 1
    click.echo(f"Terminology imported: {count} terms")


@term_group.command("export")
@click.argument("project_dir", required=False, type=click.Path(exists=True, path_type=Path), default=Path("."))
@click.argument("output_file", required=False, type=click.Path(path_type=Path), default=None)
def term_export(project_dir: Path, output_file: Path | None):
    """Export terms to JSON file, or to terminology/terms.toml in project directory."""
    import json

    from mga.memory.state import StateManager

    if output_file is None:
        output_file = project_dir / "terminology" / "terms.toml"
        output_file.parent.mkdir(parents=True, exist_ok=True)

    terms = StateManager.list_terms(project_dir)
    data = [t.model_dump() for t in terms]
    output_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    click.echo(f"Terminology exported")


# Also expose as top-level command
term = term_group