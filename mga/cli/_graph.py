"""Character graph CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import click

from mga.memory.graph import CharacterGraph
from mga.memory.graph_retrieval import GraphRetrieval


@click.group(name="graph")
def graph_group():
    """Character relationship graph commands."""
    pass


@graph_group.command(name="add")
@click.argument("project_dir", type=click.Path(path_type=Path))
@click.argument("source")
@click.argument("target")
@click.option("--relationship", "relationship", default="")
@click.option(
    "--formality",
    default="casual",
    type=click.Choice(["intimate", "casual", "polite", "formal", "honorific"]),
    show_default=True,
)
@click.option("--honorific", default="")
@click.option("--notes", default="")
def graph_add(
    project_dir: Path,
    source: str,
    target: str,
    relationship: str,
    formality: str,
    honorific: str,
    notes: str,
):
    """Add or update a directed character relationship."""
    character_graph = CharacterGraph.load(project_dir)
    character_graph.add_character(source)
    character_graph.add_character(target)
    character_graph.add_relationship(
        source,
        target,
        relationship=relationship,
        formality=formality,
        honorific=honorific,
        notes=notes,
    )
    character_graph.save(project_dir)
    click.echo(f"Relationship saved: {source} -> {target}")


@graph_group.command(name="list")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path))
@click.option("--character", "character_filter", default=None, help="Filter by character id")
def graph_list(project_dir: Path, character_filter: str | None):
    """List character relationship edges."""
    character_graph = CharacterGraph.load(project_dir)
    edges = [
        (src, tgt, data)
        for src, tgt, data in character_graph.graph.edges(data=True)
        if character_filter is None or src == character_filter or tgt == character_filter
    ]
    if not edges:
        click.echo("No character relationships found.")
        return
    for src, tgt, data in edges:
        details = []
        if data.get("relationship"):
            details.append(data["relationship"])
        if data.get("formality"):
            details.append(f"formality={data['formality']}")
        if data.get("honorific"):
            details.append(f"honorific={data['honorific']}")
        if data.get("notes"):
            details.append(f"notes={data['notes']}")
        suffix = f" ({', '.join(details)})" if details else ""
        click.echo(f"  {src} -> {tgt}{suffix}")


@graph_group.command(name="context")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path))
@click.argument("speaker")
@click.argument("listener")
@click.option("--json", "as_json", is_flag=True, help="Emit structured JSON")
def graph_context(
    project_dir: Path,
    speaker: str,
    listener: str,
    as_json: bool,
):
    """Retrieve speaker/listener relationship context."""
    retrieval = GraphRetrieval.from_project(project_dir)
    addressing = retrieval.get_addressing(speaker, listener)
    prompt_context = retrieval.get_translation_context(speaker, listener)
    payload = {
        "speaker": speaker,
        "listener": listener,
        **addressing,
        "prompt_context": prompt_context,
    }
    if as_json:
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    click.echo(f"{speaker} -> {listener}")
    click.echo(f"relationship: {payload['relationship'] or '(none)'}")
    click.echo(f"formality: {payload['formality']}")
    click.echo(f"honorific: {payload['honorific'] or '(none)'}")
    click.echo(f"suggestion: {payload['suggestion']}")
    if prompt_context:
        click.echo(f"context: {prompt_context}")


@graph_group.command(name="check-formality")
@click.argument("project_dir", type=click.Path(exists=True, path_type=Path))
@click.argument("speaker")
@click.argument("listener")
@click.argument(
    "proposed_formality",
    type=click.Choice(["intimate", "casual", "polite", "formal", "honorific"]),
)
@click.option("--json", "as_json", is_flag=True, help="Emit structured JSON")
def graph_check_formality(
    project_dir: Path,
    speaker: str,
    listener: str,
    proposed_formality: str,
    as_json: bool,
):
    """Check whether proposed formality matches graph context."""
    result = GraphRetrieval.from_project(project_dir).check_formality_consistency(
        speaker,
        listener,
        proposed_formality,
    )
    payload = {
        "speaker": speaker,
        "listener": listener,
        **result,
    }
    if as_json:
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    status = "consistent" if result["consistent"] else "mismatch"
    click.echo(
        f"Formality {status}: expected={result['expected']} "
        f"proposed={result['proposed']}"
    )
    click.echo(result["message"])