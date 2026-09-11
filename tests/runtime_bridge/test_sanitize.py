from __future__ import annotations

import pytest
from PIL import Image

from mga.runtime_bridge.external import (
    _build_external_child_env,
    _run_export_artifact_command,
    _sanitize_subprocess_output,
    run_export_artifact,
    run_render_only,
)


def test_sanitize_subprocess_output_redacts_openai_style_keys() -> None:
    fake_key = "sk-proj-" + "FAKE1234" * 4
    output = f"failed with key {fake_key}"

    sanitized = _sanitize_subprocess_output(output)

    assert fake_key not in sanitized
    assert "[REDACTED]" in sanitized


def test_sanitize_subprocess_output_redacts_bearer_tokens() -> None:
    output = "Authorization: Bearer abcDEF1234567890"

    sanitized = _sanitize_subprocess_output(output)

    assert sanitized == "Authorization: Bearer [REDACTED]"


def test_sanitize_subprocess_output_redacts_secret_assignments() -> None:
    output = "OPENAI_API_KEY=secret-value stderr tail"

    sanitized = _sanitize_subprocess_output(output)

    assert sanitized == "OPENAI_API_KEY=[REDACTED] stderr tail"


def test_sanitize_subprocess_output_redacts_secret_query_parameters() -> None:
    output = "GET https://example.test/v1?api_key=secret-value&ok=1"

    sanitized = _sanitize_subprocess_output(output)

    assert sanitized == "GET https://example.test/v1?api_key=[REDACTED]&ok=1"


def test_sanitize_subprocess_output_preserves_empty_string() -> None:
    assert _sanitize_subprocess_output("") == ""


def test_sanitize_subprocess_output_preserves_non_secret_content() -> None:
    output = "INFO: processed 12 pages without credentials"

    assert _sanitize_subprocess_output(output) == output


def test_build_external_child_env_strips_api_key_environment(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "host-secret")
    monkeypatch.setenv("CUSTOM_API_KEY", "custom-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "github-secret")
    monkeypatch.setenv("SAFE_SETTING", "safe")

    child_env = _build_external_child_env()

    assert "OPENAI_API_KEY" not in child_env
    assert "CUSTOM_API_KEY" not in child_env
    assert "GITHUB_TOKEN" not in child_env
    assert child_env["SAFE_SETTING"] == "safe"


def test_run_export_artifact_failure_sanitizes_captured_output(tmp_path, monkeypatch) -> None:
    image = tmp_path / "page.png"
    Image.new("RGB", (8, 8), "white").save(image)

    class Completed:
        returncode = 1
        stdout = "OPENAI_API_KEY=secret-value\n"
        stderr = "Authorization: Bearer abcDEF1234567890\n"

    monkeypatch.setattr("mga.runtime_bridge.external.subprocess.run", lambda *args, **kwargs: Completed())

    with pytest.raises(RuntimeError) as exc_info:
        run_export_artifact(input_dir=image, payload_dir=tmp_path / "payload")

    message = str(exc_info.value)
    assert "secret-value" not in message
    assert "abcDEF1234567890" not in message
    assert "[REDACTED]" in message


def test_run_export_artifact_failure_handles_missing_captured_output(tmp_path, monkeypatch) -> None:
    image = tmp_path / "page.png"
    Image.new("RGB", (8, 8), "white").save(image)

    class Completed:
        returncode = 1
        stdout = None
        stderr = None

    monkeypatch.setattr("mga.runtime_bridge.external.subprocess.run", lambda *args, **kwargs: Completed())

    with pytest.raises(RuntimeError) as exc_info:
        run_export_artifact(input_dir=image, payload_dir=tmp_path / "payload")

    message = str(exc_info.value)
    assert "Export artifact failed for page 0 (exit 1)" in message
    assert "NoneType" not in message


def test_run_export_artifact_command_uses_utf8_replace_decode(tmp_path, monkeypatch) -> None:
    captured_kwargs = {}

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        captured_kwargs.update(kwargs)
        return Completed()

    monkeypatch.setattr("mga.runtime_bridge.external.subprocess.run", fake_run)

    _run_export_artifact_command(
        external_python=tmp_path / "python.exe",
        resolved_repo=tmp_path,
        runtime_input=tmp_path / "page.png",
        output_dir=tmp_path / "out",
        payload_dir=tmp_path / "payload",
        export_config_path=tmp_path / "config.json",
    )

    assert captured_kwargs["text"] is True
    assert captured_kwargs["encoding"] == "utf-8"
    assert captured_kwargs["errors"] == "replace"
    assert captured_kwargs["capture_output"] is True


def test_run_render_only_failure_sanitizes_captured_output(tmp_path, monkeypatch) -> None:
    class Completed:
        returncode = 1
        stdout = ""
        stderr = "stderr OPENAI_API_KEY=secret-value"

    monkeypatch.setattr("mga.runtime_bridge.external.subprocess.run", lambda *args, **kwargs: Completed())

    with pytest.raises(RuntimeError) as exc_info:
        run_render_only(payload_dir=tmp_path / "payload", output_dir=tmp_path / "out")

    message = str(exc_info.value)
    assert "secret-value" not in message
    assert "OPENAI_API_KEY=[REDACTED]" in message


def test_run_render_only_failure_handles_missing_captured_output(tmp_path, monkeypatch) -> None:
    class Completed:
        returncode = 1
        stdout = None
        stderr = None

    monkeypatch.setattr("mga.runtime_bridge.external.subprocess.run", lambda *args, **kwargs: Completed())

    with pytest.raises(RuntimeError) as exc_info:
        run_render_only(payload_dir=tmp_path / "payload", output_dir=tmp_path / "out")

    message = str(exc_info.value)
    assert "Render-only failed (exit 1)" in message
    assert "NoneType" not in message
