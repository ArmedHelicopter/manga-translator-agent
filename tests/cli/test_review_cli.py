from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from manga_translate.cli import main as compat_main
from mga.cli.main import main


def _write_candidates(path: Path, candidates: list[dict[str, object]]) -> None:
    path.write_text(
        json.dumps(candidates, ensure_ascii=False),
        encoding="utf-8",
    )


def test_review_diff_cli_writes_diff_artifact(tmp_path: Path) -> None:
    runner = CliRunner()
    original_path = tmp_path / "original.json"
    revised_path = tmp_path / "revised.json"
    output_dir = tmp_path / "output"
    _write_candidates(
        original_path,
        [
            {"bubble_id": "b1", "text": "old"},
            {"bubble_id": "b2", "text": "same"},
        ],
    )
    _write_candidates(
        revised_path,
        [
            {"bubble_id": "b1", "text": "new"},
            {"bubble_id": "b2", "text": "same"},
        ],
    )

    result = runner.invoke(
        main,
        ["review", "diff", str(original_path), str(revised_path), "-o", str(output_dir)],
    )

    assert result.exit_code == 0, result.output
    assert "1/2 bubbles changed" in result.output
    payload = json.loads((output_dir / "review" / "diff.json").read_text(encoding="utf-8"))
    assert payload["changed_bubbles"] == 1
    assert payload["changes"][0]["bubble_id"] == "b1"


def test_review_diff_cli_preserves_translation_report_context(tmp_path: Path) -> None:
    runner = CliRunner()
    original_path = tmp_path / "original-report.json"
    revised_path = tmp_path / "revised-report.json"
    output_dir = tmp_path / "output"
    original_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "bubble_id": "b1",
                        "page_id": "p1",
                        "source_text": "source",
                        "translated_text": "old",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    revised_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "bubble_id": "b1",
                        "page_id": "p1",
                        "source_text": "source",
                        "translated_text": "new",
                        "needs_human_review": True,
                        "qa_findings": [{"bubble_id": "b1", "message": "check"}],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        main,
        ["review", "diff", str(original_path), str(revised_path), "-o", str(output_dir)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads((output_dir / "review" / "diff.json").read_text(encoding="utf-8"))
    change = payload["changes"][0]
    assert change["page_id"] == "p1"
    assert change["source_text"] == "source"
    assert change["needs_human_review"] is True
    assert change["qa_findings"][0]["message"] == "check"


def test_review_diff_compatibility_cli_writes_diff_artifact(tmp_path: Path) -> None:
    runner = CliRunner()
    original_path = tmp_path / "original.json"
    revised_path = tmp_path / "revised.json"
    output_dir = tmp_path / "compat-output"
    _write_candidates(original_path, [{"bubble_id": "b1", "text": "old"}])
    _write_candidates(revised_path, [{"bubble_id": "b1", "text": "new"}])

    result = runner.invoke(
        compat_main,
        ["review", "diff", str(original_path), str(revised_path), "-o", str(output_dir)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads((output_dir / "review" / "diff.json").read_text(encoding="utf-8"))
    assert payload["changes"][0]["change_type"] == "changed"


def test_review_report_cli_writes_review_report_artifact(tmp_path: Path) -> None:
    runner = CliRunner()
    report_path = tmp_path / "translation-report.json"
    output_dir = tmp_path / "review-output"
    report_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "bubble_id": "b1",
                        "page_id": "p1",
                        "source_text": "source",
                        "translated_text": "translation",
                        "qa_findings": [
                            {
                                "bubble_id": "b1",
                                "feedback_type": "error",
                                "message": "wrong fact",
                                "confidence": 0.9,
                            }
                        ],
                        "needs_human_review": True,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        main,
        ["review", "report", str(report_path), "-o", str(output_dir)],
    )

    assert result.exit_code == 0, result.output
    assert "1 pages, 1 needing human review" in result.output
    payload = json.loads((output_dir / "review" / "report.json").read_text(encoding="utf-8"))
    assert payload["summary"]["total_pages"] == 1
    assert payload["summary"]["pages_needing_human_review"] == 1
    assert payload["reports"][0]["page_id"] == "p1"
    assert payload["reports"][0]["qa_feedbacks"][0]["feedback_type"] == "error"


def test_review_repair_plan_cli_writes_repair_plan_artifact(tmp_path: Path) -> None:
    runner = CliRunner()
    report_path = tmp_path / "translation-report.json"
    output_dir = tmp_path / "repair-output"
    report_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "bubble_id": "b1",
                        "page_id": "p1",
                        "repair_plan": [
                            {
                                "bubble_id": "b1",
                                "category": "fact.number_mismatch",
                                "feedback_type": "warning",
                                "target": "semantic",
                                "action": "repair_semantic_translation",
                                "message": "wrong number",
                            }
                        ],
                    },
                    {
                        "bubble_id": "b2",
                        "page_id": "p1",
                        "repair_plan": [
                            {
                                "bubble_id": "b2",
                                "category": "character.voice",
                                "feedback_type": "warning",
                                "target": "persona",
                                "action": "repair_persona_rendering",
                                "message": "voice drift",
                            }
                        ],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        main,
        ["review", "repair-plan", str(report_path), "-o", str(output_dir)],
    )

    assert result.exit_code == 0, result.output
    assert "2 repairs" in result.output
    payload = json.loads((output_dir / "review" / "repair-plan.json").read_text(encoding="utf-8"))
    assert payload["summary"]["total_repairs"] == 2
    assert payload["summary"]["targets"] == {"semantic": 1, "persona": 1}
    assert payload["summary"]["actions"] == {
        "repair_semantic_translation": 1,
        "repair_persona_rendering": 1,
    }
    assert payload["repairs"][0]["bubble_id"] == "b1"
    assert payload["repairs"][1]["target"] == "persona"


def test_review_decide_cli_records_repair_decision(tmp_path: Path) -> None:
    runner = CliRunner()
    repair_plan_path = tmp_path / "repair-plan.json"
    project_dir = tmp_path / "project"
    repair_plan_path.write_text(
        json.dumps(
            {
                "repairs": [
                    {
                        "bubble_id": "b1",
                        "page_id": "p1",
                        "target": "semantic",
                        "action": "repair_semantic_translation",
                        "message": "wrong number",
                        "confidence": 0.82,
                        "original_text": "old number",
                        "suggested_text": "new number",
                        "rationale": "number should match source",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        main,
        [
            "review",
            "decide",
            str(repair_plan_path),
            "--project-dir",
            str(project_dir),
            "--bubble-id",
            "b1",
            "--status",
            "accept",
            "--rationale",
            "Human reviewer confirmed the semantic repair.",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Review decision saved: review-p1-b1-accept" in result.output
    payload = json.loads(
        (
            project_dir
            / "memory"
            / "state"
            / "decisions"
            / "review-p1-b1-accept.json"
        ).read_text(encoding="utf-8")
    )
    assert payload["stage"] == "review"
    assert payload["input_ref"] == "p1/b1"
    assert payload["decision"] == "accept repair_semantic_translation for b1"
    assert payload["rationale"] == "Human reviewer confirmed the semantic repair."
    assert payload["confidence"] == 0.82
    assert payload["metadata"] == {
        "page_id": "p1",
        "bubble_id": "b1",
        "target": "semantic",
        "action": "repair_semantic_translation",
        "message": "wrong number",
        "original_text": "old number",
        "suggested_text": "new number",
        "repair_rationale": "number should match source",
        "status": "accept",
    }
