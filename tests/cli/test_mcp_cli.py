from __future__ import annotations

from click.testing import CliRunner

from mga.cli.main import main


def test_mcp_cli_help_lists_project_root_option():
    result = CliRunner().invoke(main, ["mcp", "--help"])

    assert result.exit_code == 0
    assert "--project-root" in result.output


def test_mcp_cli_invokes_stdio_server_with_project_root(tmp_path, monkeypatch):
    captured = {}

    def fake_run_stdio(server):
        captured["project_root"] = server.project_root

    monkeypatch.setattr("mga.mcp_server.run_stdio", fake_run_stdio)

    result = CliRunner().invoke(
        main,
        ["mcp", "--project-root", str(tmp_path)],
    )

    assert result.exit_code == 0, result.output
    assert captured["project_root"] == tmp_path.resolve()
