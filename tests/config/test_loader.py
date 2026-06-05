"""Tests for provider config loading."""

from __future__ import annotations

from mga.config.loader import build_project_config


def test_build_project_config_resolves_qa_route_and_env_placeholders(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_OPENAI_KEY", "resolved-key")
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        '[stages.vision]\nprimary = "openai"\n\n'
        '[stages.translation]\nprimary = "gemini"\n\n'
        '[stages.qa]\nprimary = "deepseek"\nfallback = "gemini"\n\n'
        '[providers.openai]\napi_key = "${TEST_OPENAI_KEY}"\nvision_model = "gpt-4o"\ntext_model = "gpt-4o-mini"\n\n'
        '[providers.gemini]\napi_key = "gemini-key"\nvision_model = "gemini-vision"\ntext_model = "gemini-text"\n\n'
        '[providers.deepseek]\napi_key = "deepseek-key"\nmodel = "deepseek-chat"\n',
        encoding="utf-8",
    )
    input_path = tmp_path / "input"
    input_path.mkdir()

    cfg, raw = build_project_config(
        input_path=str(input_path),
        output_path=str(tmp_path / "out"),
        provider_override=None,
        save_json=False,
        dry_run=False,
        config_path=str(config_path),
    )

    assert raw["providers"]["openai"]["api_key"] == "resolved-key"
    assert cfg.provider_routes["translation"].primary.provider == "gemini"
    assert cfg.provider_routes["qa"].primary.provider == "deepseek"
    assert cfg.provider_routes["qa"].fallback.provider == "gemini"
    assert cfg.provider_routes["qa"].primary.model == "deepseek-chat"


def test_build_project_config_defaults_qa_to_translation_route(tmp_path):
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        '[stages.vision]\nprimary = "openai"\n\n'
        '[stages.translation]\nprimary = "gemini"\n\n'
        '[providers.openai]\napi_key = "openai-key"\nvision_model = "gpt-4o"\ntext_model = "gpt-4o-mini"\n\n'
        '[providers.gemini]\napi_key = "gemini-key"\nvision_model = "gemini-vision"\ntext_model = "gemini-text"\n',
        encoding="utf-8",
    )
    input_path = tmp_path / "input"
    input_path.mkdir()

    cfg, _raw = build_project_config(
        input_path=str(input_path),
        output_path=str(tmp_path / "out"),
        provider_override=None,
        save_json=False,
        dry_run=False,
        config_path=str(config_path),
    )

    assert cfg.provider_routes["qa"].primary.provider == "gemini"
    assert cfg.provider_routes["qa"].primary.model == "gemini-text"


def test_build_project_config_allows_mimo_builtin_defaults(tmp_path):
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        '[stages.vision]\nprimary = "mimo"\n\n'
        '[stages.translation]\nprimary = "mimo"\n\n'
        '[providers.mimo]\n',
        encoding="utf-8",
    )
    input_path = tmp_path / "input"
    input_path.mkdir()

    cfg, raw = build_project_config(
        input_path=str(input_path),
        output_path=str(tmp_path / "out"),
        provider_override="mimo",
        save_json=False,
        dry_run=False,
        config_path=str(config_path),
    )

    assert raw["providers"]["mimo"] == {}
    assert cfg.provider_routes["vision"].primary.provider == "mimo"
    assert cfg.provider_routes["vision"].primary.model == "mimo-v2.5-pro"
    assert cfg.provider_routes["translation"].primary.provider == "mimo"
    assert cfg.provider_routes["translation"].primary.model == "mimo-v2.5-pro"
    assert cfg.provider_routes["qa"].primary.provider == "mimo"


def test_build_project_config_uses_project_working_dir_for_file_inputs(tmp_path):
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        '[stages.vision]\nprimary = "mimo"\n\n'
        '[stages.translation]\nprimary = "mimo"\n\n'
        '[providers.mimo]\n',
        encoding="utf-8",
    )
    input_path = tmp_path / "book.pdf"
    input_path.write_bytes(b"%PDF")
    output_path = tmp_path / "out"

    cfg, _raw = build_project_config(
        input_path=str(input_path),
        output_path=str(output_path),
        provider_override="mimo",
        save_json=False,
        dry_run=False,
        config_path=str(config_path),
    )

    assert cfg.project_name == "book"
    assert cfg.working_dir == str(output_path / ".mga-project")


def test_build_project_config_preserves_plugin_configuration(tmp_path):
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        '[stages.vision]\nprimary = "openai"\n\n'
        '[stages.translation]\nprimary = "gemini"\n\n'
        '[providers.openai]\napi_key = "openai-key"\nvision_model = "gpt-4o"\ntext_model = "gpt-4o-mini"\n\n'
        '[providers.gemini]\napi_key = "gemini-key"\nvision_model = "gemini-vision"\ntext_model = "gemini-text"\n\n'
        '[plugins.renderer]\nclass = "custom_renderers:Renderer"\nmarker = "project-renderer"\n',
        encoding="utf-8",
    )
    input_path = tmp_path / "input"
    input_path.mkdir()

    cfg, raw = build_project_config(
        input_path=str(input_path),
        output_path=str(tmp_path / "out"),
        provider_override=None,
        save_json=False,
        dry_run=False,
        config_path=str(config_path),
    )

    assert raw["plugins"]["renderer"]["class"] == "custom_renderers:Renderer"
    assert cfg.plugins["renderer"] == {
        "class": "custom_renderers:Renderer",
        "marker": "project-renderer",
    }
