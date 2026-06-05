from __future__ import annotations

from click.testing import CliRunner

from mga.cli.main import main


def test_web_cli_help_lists_project_root_option():
    result = CliRunner().invoke(main, ["web", "--help"])

    assert result.exit_code == 0
    assert "--project-root" in result.output
    assert "--host" in result.output
    assert "--port" in result.output


def test_web_cli_invokes_uvicorn_with_created_app(tmp_path, monkeypatch):
    captured = {}

    def fake_run(app, host, port):
        captured["app"] = app
        captured["host"] = host
        captured["port"] = port

    monkeypatch.setattr("uvicorn.run", fake_run)

    result = CliRunner().invoke(
        main,
        [
            "web",
            "--project-root",
            str(tmp_path),
            "--host",
            "0.0.0.0",
            "--port",
            "9001",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["host"] == "0.0.0.0"
    assert captured["port"] == 9001
    assert captured["app"].state.project_root == tmp_path
