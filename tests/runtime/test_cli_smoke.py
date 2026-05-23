from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from manga_translate.cli import main


def test_translate_external_core_writes_manifest_and_run(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()
    input_dir = Path("tests/fixtures/images/source").resolve()
    output_dir = tmp_path / "run"

    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        """
[stages.vision]
primary = "openai"

[stages.translation]
primary = "openai"

[providers.openai]
api_key = "test-key"
base_url = "https://api.openai.com/v1"
vision_model = "gpt-4o"
text_model = "gpt-4o-mini"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MANGA_TRANSLATE_CONFIG", str(config_path))
    monkeypatch.setattr(
        "manga_translate.cli.run_external_translation_runtime",
        lambda **kwargs: {
            "summary": {
                "repo_dir": "/tmp/mit",
                "saved_text_artifact": str(output_dir / "external-baseline-text.txt"),
                "normalized_text_artifact": str(output_dir / "external-baseline-text-normalized.json"),
                "rendered_images": ["sample-page-01.png"],
            }
        },
    )

    result = runner.invoke(main, ["translate", str(input_dir), "-o", str(output_dir)])

    assert result.exit_code == 0, result.output
    assert (output_dir / "run.json").exists()
    assert (output_dir / "manifest.json").exists()

    run_payload = json.loads((output_dir / "run.json").read_text(encoding="utf-8"))
    assert run_payload["translation_mode"] == "external-core"
    assert run_payload["runtime"]["type"] == "external-core"
    assert run_payload["status"] == "completed"


def test_translate_external_core_rejects_dry_run(tmp_path: Path) -> None:
    runner = CliRunner()
    input_dir = Path("tests/fixtures/images/source").resolve()
    output_dir = tmp_path / "run"

    result = runner.invoke(main, ["translate", str(input_dir), "-o", str(output_dir), "--dry-run"])

    assert result.exit_code != 0
    assert "does not support '--dry-run'" in result.output
