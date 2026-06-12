from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from mga.cli.main import main


def test_batch_run_cli_processes_chapter_manifest(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    chapters_path = tmp_path / "chapters.json"
    project_dir = tmp_path / "project"
    chapters = [
        {
            "chapter_id": "ch1",
            "input_path": str(tmp_path / "input" / "ch1"),
            "output_path": str(tmp_path / "output" / "ch1"),
        }
    ]
    chapters_path.write_text(json.dumps(chapters), encoding="utf-8")
    captured = {}

    class FakeBatchProcessor:
        def __init__(self, project_dir, **kwargs):
            captured["project_dir"] = project_dir
            captured["kwargs"] = kwargs

        def process(self, chapters_payload, resume=True):
            captured["chapters"] = chapters_payload
            captured["resume"] = resume
            return {
                "total_chapters": 1,
                "completed": 1,
                "partial": 0,
                "failed": 0,
                "total_translations": 3,
                "total_errors": 0,
                "results": {"ch1": {"status": "completed"}},
            }

    monkeypatch.setattr("mga.cli._batch.BatchProcessor", FakeBatchProcessor)

    result = runner.invoke(
        main,
        [
            "batch",
            "run",
            str(chapters_path),
            "--project-dir",
            str(project_dir),
            "--max-workers",
            "2",
            "--no-resume",
            "--provider",
            "openai",
            "--save-json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["project_dir"] == project_dir
    assert captured["kwargs"] == {
        "max_workers": 2,
        "provider_override": "openai",
        "config_path": None,
        "save_json": True,
    }
    assert captured["chapters"] == chapters
    assert captured["resume"] is False
    summary = json.loads((project_dir / "batch-summary.json").read_text(encoding="utf-8"))
    assert summary["completed"] == 1
    assert "1 completed" in result.output


def test_batch_run_cli_rejects_non_list_manifest(tmp_path: Path) -> None:
    runner = CliRunner()
    chapters_path = tmp_path / "chapters.json"
    chapters_path.write_text(json.dumps({"chapters": []}), encoding="utf-8")

    result = runner.invoke(
        main,
        ["batch", "run", str(chapters_path), "--project-dir", str(tmp_path / "project")],
    )

    assert result.exit_code != 0
    assert "chapters_json must contain a JSON list" in result.output


def test_batch_status_cli_writes_progress_summary(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    chapters_path = tmp_path / "chapters.json"
    project_dir = tmp_path / "project"
    chapters = [
        {
            "chapter_id": "ch1",
            "input_path": str(tmp_path / "input" / "ch1"),
            "output_path": str(tmp_path / "output" / "ch1"),
        },
        {
            "chapter_id": "ch2",
            "input_path": str(tmp_path / "input" / "ch2"),
            "output_path": str(tmp_path / "output" / "ch2"),
        },
    ]
    chapters_path.write_text(json.dumps(chapters), encoding="utf-8")
    captured = {}

    class FakeBatchProcessor:
        def __init__(self, project_dir, **kwargs):
            captured["project_dir"] = project_dir
            captured["kwargs"] = kwargs

        def get_status(self, chapters_payload):
            captured["chapters"] = chapters_payload
            return {
                "total_chapters": 2,
                "completed": 1,
                "partial": 0,
                "failed": 0,
                "pending": 1,
                "results": {
                    "ch1": {"status": "completed"},
                    "ch2": {"status": "pending"},
                },
            }

    monkeypatch.setattr("mga.cli._batch.BatchProcessor", FakeBatchProcessor)

    result = runner.invoke(
        main,
        ["batch", "status", str(chapters_path), "--project-dir", str(project_dir)],
    )

    assert result.exit_code == 0, result.output
    assert captured["project_dir"] == project_dir
    assert captured["chapters"] == chapters
    status = json.loads((project_dir / "batch-status.json").read_text(encoding="utf-8"))
    assert status["pending"] == 1
    assert "1 completed" in result.output
    assert "1 pending" in result.output


def test_batch_reset_cli_clears_progress(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    project_dir = tmp_path / "project"
    captured = {}

    class FakeBatchProcessor:
        def __init__(self, project_dir, **kwargs):
            captured["project_dir"] = project_dir

        def reset(self):
            captured["reset"] = True

    monkeypatch.setattr("mga.cli._batch.BatchProcessor", FakeBatchProcessor)

    result = runner.invoke(main, ["batch", "reset", "--project-dir", str(project_dir)])

    assert result.exit_code == 0, result.output
    assert captured == {"project_dir": project_dir, "reset": True}
    assert "Batch progress reset" in result.output
