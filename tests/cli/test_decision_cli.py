from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from mga.cli.main import main


def _read_decision(project_dir: Path, decision_id: str) -> dict:
    path = project_dir / "memory" / "state" / "decisions" / f"{decision_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_decision_add_records_translation_decision(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "decision",
            "add",
            str(tmp_path),
            "--decision-id",
            "honorific-policy",
            "--stage",
            "translate",
            "--input-ref",
            "ch1/p3",
            "--decision",
            "Preserve senpai as a relationship marker",
            "--rationale",
            "The term carries hierarchy important to later chapters",
            "--confidence",
            "0.85",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Decision saved: honorific-policy" in result.output
    payload = _read_decision(tmp_path, "honorific-policy")
    assert payload["stage"] == "translate"
    assert payload["input_ref"] == "ch1/p3"
    assert payload["decision"] == "Preserve senpai as a relationship marker"
    assert payload["rationale"] == "The term carries hierarchy important to later chapters"
    assert payload["confidence"] == 0.85


def test_decision_list_prints_recorded_decisions(tmp_path: Path) -> None:
    runner = CliRunner()
    add_result = runner.invoke(
        main,
        [
            "decision",
            "add",
            str(tmp_path),
            "--decision-id",
            "style-policy",
            "--stage",
            "persona",
            "--decision",
            "Use clipped lines for Ren",
            "--confidence",
            "0.7",
        ],
    )
    assert add_result.exit_code == 0, add_result.output

    result = runner.invoke(main, ["decision", "list", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "style-policy" in result.output
    assert "[persona] Use clipped lines for Ren" in result.output
