from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from mga.cli.main import main
from mga.memory.graph import CharacterGraph


def test_graph_add_records_relationship_edge(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "graph",
            "add",
            str(tmp_path),
            "akari",
            "ren",
            "--relationship",
            "rival",
            "--formality",
            "polite",
            "--honorific",
            "san",
            "--notes",
            "Akari keeps distance in early chapters",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Relationship saved: akari -> ren" in result.output
    graph = CharacterGraph.load(tmp_path)
    edge = graph.get_relationship("akari", "ren")
    assert edge is not None
    assert edge["relationship"] == "rival"
    assert edge["formality"] == "polite"
    assert edge["honorific"] == "san"
    assert edge["notes"] == "Akari keeps distance in early chapters"


def test_graph_list_prints_relationship_edges(tmp_path: Path) -> None:
    runner = CliRunner()
    graph = CharacterGraph()
    graph.add_relationship(
        "akari",
        "ren",
        relationship="rival",
        formality="formal",
        honorific="kun",
    )
    graph.save(tmp_path)

    result = runner.invoke(main, ["graph", "list", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "akari -> ren" in result.output
    assert "rival" in result.output
    assert "formal" in result.output
    assert "kun" in result.output


def test_graph_list_can_filter_by_character(tmp_path: Path) -> None:
    runner = CliRunner()
    graph = CharacterGraph()
    graph.add_relationship("akari", "ren", relationship="rival")
    graph.add_relationship("ren", "akari", relationship="rival")
    graph.add_relationship("ren", "mentor", relationship="student")
    graph.save(tmp_path)

    result = runner.invoke(
        main,
        ["graph", "list", str(tmp_path), "--character", "akari"],
    )

    assert result.exit_code == 0, result.output
    assert "akari -> ren" in result.output
    assert "ren -> akari" in result.output
    assert "ren -> mentor" not in result.output


def test_graph_context_prints_relationship_context(tmp_path: Path) -> None:
    runner = CliRunner()
    graph = CharacterGraph()
    graph.add_relationship(
        "akari",
        "ren",
        relationship="rival",
        formality="formal",
        honorific="kun",
    )
    graph.save(tmp_path)

    result = runner.invoke(main, ["graph", "context", str(tmp_path), "akari", "ren"])

    assert result.exit_code == 0, result.output
    assert "akari -> ren" in result.output
    assert "relationship: rival" in result.output
    assert "formality: formal" in result.output
    assert "honorific: kun" in result.output
    assert "context:" in result.output


def test_graph_context_can_emit_json(tmp_path: Path) -> None:
    runner = CliRunner()
    graph = CharacterGraph()
    graph.add_relationship("akari", "ren", relationship="rival", formality="polite")
    graph.save(tmp_path)

    result = runner.invoke(
        main,
        ["graph", "context", str(tmp_path), "akari", "ren", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["speaker"] == "akari"
    assert payload["listener"] == "ren"
    assert payload["relationship"] == "rival"
    assert payload["formality"] == "polite"
    assert payload["prompt_context"]


def test_graph_check_formality_reports_consistency(tmp_path: Path) -> None:
    runner = CliRunner()
    graph = CharacterGraph()
    graph.add_relationship("akari", "ren", relationship="rival", formality="formal")
    graph.save(tmp_path)

    result = runner.invoke(
        main,
        ["graph", "check-formality", str(tmp_path), "akari", "ren", "casual"],
    )

    assert result.exit_code == 0, result.output
    assert "Formality mismatch" in result.output
    assert "expected=formal" in result.output
    assert "proposed=casual" in result.output
