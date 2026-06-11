from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from mga.cli.main import main
from mga.memory.entities import TermState
from mga.memory.state import StateManager


def _read_term(project_dir: Path, term_id: str) -> dict:
    path = project_dir / "memory" / "state" / "terms" / f"{term_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_term_edit_creates_terminology_entry(tmp_path: Path) -> None:
    runner = CliRunner()

    result = runner.invoke(
        main,
        [
            "term",
            "edit",
            str(tmp_path),
            "glass_joining",
            "--term-jp",
            "硝子継ぎ",
            "--term-zh",
            "玻璃续接",
            "--context",
            "worldbuilding term",
            "--cultural-weight",
            "G4",
            "--strategy",
            "literal",
            "--frequency",
            "3",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Term saved: glass_joining" in result.output
    term = _read_term(tmp_path, "glass_joining")
    assert term == {
        "term_id": "glass_joining",
        "candidate_translations": [],
        "term_jp": "硝子継ぎ",
        "term_zh": "玻璃续接",
        "context": "worldbuilding term",
        "cultural_weight": "G4",
        "strategy": "literal",
        "accepted_reason": "",
        "rejected_reasons": {},
        "applicability_scope": "",
        "provenance": {},
        "pending_human_review": False,
        "frequency": 3,
        "grade": "",
        "status": "",
    }


def test_term_edit_updates_existing_terminology_entry(tmp_path: Path) -> None:
    runner = CliRunner()
    first = runner.invoke(
        main,
        [
            "term",
            "edit",
            str(tmp_path),
            "katana",
            "--term-jp",
            "刀",
            "--term-zh",
            "刀",
            "--frequency",
            "1",
        ],
    )
    assert first.exit_code == 0, first.output

    second = runner.invoke(
        main,
        [
            "term",
            "edit",
            str(tmp_path),
            "katana",
            "--term-zh",
            "武士刀",
            "--strategy",
            "preserve",
        ],
    )

    assert second.exit_code == 0, second.output
    term = _read_term(tmp_path, "katana")
    assert term["term_jp"] == "刀"
    assert term["term_zh"] == "武士刀"
    assert term["strategy"] == "preserve"
    assert term["frequency"] == 1


def test_term_list_defaults_to_current_directory(tmp_path: Path) -> None:
    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=str(tmp_path)):
        StateManager.upsert_term(
            Path("."),
            TermState(
                term_id="katana",
                term_jp="katana",
                term_zh="sword",
                frequency=2,
            ),
        )

        result = runner.invoke(main, ["term", "list"])

        assert result.exit_code == 0, result.output
        assert "katana: katana -> sword" in result.output


def test_term_export_writes_toml_terminology(tmp_path: Path) -> None:
    runner = CliRunner()
    edit_result = runner.invoke(
        main,
        [
            "term",
            "edit",
            str(tmp_path),
            "katana",
            "--term-jp",
            "katana",
            "--term-zh",
            "sword",
            "--context",
            "weapon term",
            "--cultural-weight",
            "weapon",
            "--strategy",
            "preserve",
        ],
    )
    assert edit_result.exit_code == 0, edit_result.output

    result = runner.invoke(main, ["term", "export", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Terminology exported" in result.output
    terms_toml = (tmp_path / "terminology" / "terms.toml").read_text(encoding="utf-8")
    assert "katana" in terms_toml
    assert "sword" in terms_toml
    assert "preserve" in terms_toml


def test_term_export_preserves_review_fields(tmp_path: Path) -> None:
    runner = CliRunner()
    StateManager.upsert_term(
        tmp_path,
        TermState(
            term_id="glass_join",
            term_jp="glass join",
            term_zh="glass mending",
            context="fictional repair term",
            candidate_translations=["glass mending", "crystal join"],
            accepted_reason="Matches established ritual term.",
            rejected_reasons={"crystal join": "Sounds like a material name."},
            applicability_scope="Use for the named repair art only.",
        ),
    )

    result = runner.invoke(main, ["term", "export", str(tmp_path)])

    assert result.exit_code == 0, result.output
    terms_toml = (tmp_path / "terminology" / "terms.toml").read_text(encoding="utf-8")
    assert "candidate_translations" in terms_toml
    assert "accepted_reason" in terms_toml
    assert "rejected_reasons" in terms_toml
    assert "applicability_scope" in terms_toml


def test_term_import_reads_toml_terminology(tmp_path: Path) -> None:
    runner = CliRunner()
    term_dir = tmp_path / "terminology"
    term_dir.mkdir()
    (term_dir / "terms.toml").write_text(
        '[terms]\n'
        'katana = { term_jp = "katana", term_target = "sword", strategy = "preserve", notes = "weapon term", problem_types = ["weapon"] }\n',
        encoding="utf-8",
    )

    result = runner.invoke(main, ["term", "import", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Terminology imported: 1 terms" in result.output
    term = _read_term(tmp_path, "katana")
    assert term["term_jp"] == "katana"
    assert term["term_zh"] == "sword"
    assert term["context"] == "weapon term"
    assert term["cultural_weight"] == "weapon"
    assert term["strategy"] == "preserve"


def test_term_import_preserves_review_fields(tmp_path: Path) -> None:
    runner = CliRunner()
    term_dir = tmp_path / "terminology"
    term_dir.mkdir()
    (term_dir / "terms.toml").write_text(
        '[terms]\n'
        'glass_join = { term_jp = "glass join", term_target = "glass mending", '
        'notes = "fictional repair term", '
        'candidate_translations = ["glass mending", "crystal join"], '
        'accepted_reason = "Matches established ritual term.", '
        'rejected_reasons = { "crystal join" = "Sounds like a material name." }, '
        'applicability_scope = "Use for the named repair art only." }\n',
        encoding="utf-8",
    )

    result = runner.invoke(main, ["term", "import", str(tmp_path)])

    assert result.exit_code == 0, result.output
    term = _read_term(tmp_path, "glass_join")
    assert term["candidate_translations"] == ["glass mending", "crystal join"]
    assert term["accepted_reason"] == "Matches established ritual term."
    assert term["rejected_reasons"] == {
        "crystal join": "Sounds like a material name.",
    }
    assert term["applicability_scope"] == "Use for the named repair art only."
