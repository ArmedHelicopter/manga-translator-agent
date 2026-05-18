from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from manga_translate.cli import main


def test_benchmark_extraction_failure_writes_run_log(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "001.png").write_bytes(b"fake image data")
    output_dir = tmp_path / "output"

    monkeypatch.setattr(
        "manga_translate.cli.build_project_config",
        lambda **kwargs: (
            type(
                "ProjectConfigStub",
                (),
                {
                    "artifact_dir": str(output_dir),
                    "provider_routes": {"vision": type("VisionRoute", (), {"primary": type("Primary", (), {"provider": "openai"})()})()},
                },
            )(),
            {"providers": {"openai": {}}, "stages": {}},
        ),
    )
    monkeypatch.setattr("manga_translate.cli.build_legacy_provider", lambda raw_config, primary_provider: object())
    monkeypatch.setattr("manga_translate.cli.ingest_pages", lambda project_config, store: ([], None))
    monkeypatch.setattr(
        "manga_translate.cli.run_extraction_benchmark",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("synthetic benchmark failure")),
    )

    result = runner.invoke(
        main,
        [
            "legacy",
            "benchmark-extraction",
            str(input_dir),
            "-o",
            str(output_dir),
        ],
    )

    assert result.exit_code != 0
    run_payload = json.loads((output_dir / "benchmark" / "run.json").read_text(encoding="utf-8"))
    assert run_payload["status"] == "failed"
    assert run_payload["error"] == "synthetic benchmark failure"


def test_benchmark_external_success_writes_reports(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "001.png").write_bytes(b"fake image data")
    output_dir = tmp_path / "output"

    monkeypatch.setattr(
        "manga_translate.cli.run_manga_image_translator_baseline",
        lambda **kwargs: {
            "repo_dir": "/tmp/mit",
            "saved_text_artifact": str(output_dir / "external-baseline-text.txt"),
            "normalized_text_artifact": str(output_dir / "external-baseline-text-normalized.json"),
            "parsed_page_count": 1,
        },
    )
    (output_dir).mkdir(parents=True, exist_ok=True)
    (output_dir / "external-baseline-text-normalized.json").write_text(
        json.dumps(
            [
                {
                    "page_id": "page-0001",
                    "image_path": str((input_dir / "001.png").resolve()),
                    "source_text_joined": "原文",
                    "translated_text_joined": "外部译文",
                    "region_count": 1,
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "manga_translate.cli.build_project_config",
        lambda **kwargs: (
            type(
                "ProjectConfigStub",
                (),
                {
                    "artifact_dir": str(output_dir),
                    "provider_routes": {"vision": type("VisionRoute", (), {"primary": type("Primary", (), {"provider": "openai"})()})()},
                },
            )(),
            {"providers": {"openai": {}}, "stages": {}},
        ),
    )
    monkeypatch.setattr("manga_translate.cli.build_legacy_provider", lambda raw_config, primary_provider: object())
    monkeypatch.setattr(
        "manga_translate.cli.ingest_pages",
        lambda project_config, store: (
            [
                type(
                    "PageStub",
                    (),
                    {
                        "page_id": "page-0001",
                        "image": type("ImageStub", (), {"path": str((input_dir / '001.png').resolve())})(),
                    },
                )()
            ],
            None,
        ),
    )
    monkeypatch.setattr(
        "manga_translate.cli.run_translation_benchmark",
        lambda **kwargs: {
            "page_count": 1,
            "vision_modes": ["structured", "direct"],
            "annotation_template": "benchmark/annotations.translation.template.json",
            "comparisons": [
                {
                    "page_id": "page-0001",
                    "image_path": str((input_dir / "001.png").resolve()),
                    "reference_text": None,
                    "vision": {
                        "structured": {
                            "artifact": "benchmark/translation/structured/page-0001.json",
                            "unit_count": 1,
                            "non_empty_unit_count": 1,
                            "line_count": 1,
                            "character_count": 2,
                            "joined_text": "内部结构化",
                            "score": None,
                        },
                        "direct": {
                            "artifact": "benchmark/translation/direct/page-0001.json",
                            "unit_count": 1,
                            "non_empty_unit_count": 1,
                            "line_count": 1,
                            "character_count": 2,
                            "joined_text": "内部直翻",
                            "score": None,
                        },
                    },
                }
            ],
        },
    )
    monkeypatch.setattr(
        "manga_translate.cli.run_external_translation_benchmark",
        lambda **kwargs: {"page_count": 1},
    )

    result = runner.invoke(
        main,
        [
            "benchmark-external",
            str(input_dir),
            "-o",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0
    run_payload = json.loads((output_dir / "benchmark" / "run.json").read_text(encoding="utf-8"))
    assert run_payload["status"] == "completed"
    assert run_payload["compare_with_internal"] is True
    assert run_payload["parsed_page_count"] == 1
    assert run_payload["external_translation_report"] == "benchmark/external-translation-report.json"


def test_benchmark_external_failure_writes_run_log(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "001.png").write_bytes(b"fake image data")
    output_dir = tmp_path / "output"

    monkeypatch.setattr(
        "manga_translate.cli.run_manga_image_translator_baseline",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("external benchmark failed")),
    )

    result = runner.invoke(
        main,
        [
            "benchmark-external",
            str(input_dir),
            "-o",
            str(output_dir),
            "--no-compare-with-internal",
        ],
    )

    assert result.exit_code != 0
    run_payload = json.loads((output_dir / "benchmark" / "run.json").read_text(encoding="utf-8"))
    assert run_payload["status"] == "failed"
    assert run_payload["error"] == "external benchmark failed"
