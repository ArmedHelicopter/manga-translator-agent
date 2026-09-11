"""Tests for provider config loading."""

from __future__ import annotations

import os

from mga.config.loader import build_project_config, load_provider_settings


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


def test_load_provider_settings_loads_local_dotenv_without_overwriting_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXISTING_COMPAT_KEY", "process-key")
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "LOCAL_COMPAT_KEY='dotenv-key'",
                "EXISTING_COMPAT_KEY=dotenv-should-not-win",
                "LOCAL_COMPAT_BASE_URL=http://compatible.local/v1",
            ]
        ),
        encoding="utf-8",
    )
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config_path = config_dir / "providers.toml"
    config_path.write_text(
        '[stages.vision]\nprimary = "compatible"\n\n'
        '[stages.translation]\nprimary = "compatible"\n\n'
        '[providers.compatible]\n'
        'provider_type = "openai"\n'
        'api_key_env = "LOCAL_COMPAT_KEY"\n'
        'base_url_env = "LOCAL_COMPAT_BASE_URL"\n'
        'vision_model = "compatible-vision"\n'
        'text_model = "compatible-text"\n\n'
        '[providers.existing]\n'
        'provider_type = "openai"\n'
        'api_key_env = "EXISTING_COMPAT_KEY"\n'
        'base_url = "http://existing.local/v1"\n'
        'model = "existing-model"\n',
        encoding="utf-8",
    )

    raw = load_provider_settings(str(config_path))

    assert raw["providers"]["compatible"]["api_key_env"] == "LOCAL_COMPAT_KEY"
    assert raw["providers"]["compatible"]["base_url_env"] == "LOCAL_COMPAT_BASE_URL"
    assert raw["providers"]["existing"]["api_key_env"] == "EXISTING_COMPAT_KEY"
    assert os.environ["LOCAL_COMPAT_KEY"] == "dotenv-key"
    assert os.environ["LOCAL_COMPAT_BASE_URL"] == "http://compatible.local/v1"
    assert os.environ["EXISTING_COMPAT_KEY"] == "process-key"


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
    assert cfg.provider_routes["vision"].primary.model == "mimo-v2.5"
    assert cfg.provider_routes["translation"].primary.provider == "mimo"
    assert cfg.provider_routes["translation"].primary.model == "mimo-v2.5-pro"
    assert cfg.provider_routes["qa"].primary.provider == "mimo"


def test_build_project_config_allows_openai_compatible_provider_type(tmp_path):
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        '[stages.vision]\nprimary = "compatible"\n\n'
        '[stages.translation]\nprimary = "compatible"\n\n'
        '[providers.compatible]\n'
        'provider_type = "openai"\n'
        'api_key_env = "COMPATIBLE_API_KEY"\n'
        'base_url = "https://compatible.example/v1"\n'
        'vision_model = "compatible-vision"\n'
        'text_model = "compatible-text"\n',
        encoding="utf-8",
    )
    input_path = tmp_path / "input"
    input_path.mkdir()

    cfg, raw = build_project_config(
        input_path=str(input_path),
        output_path=str(tmp_path / "out"),
        provider_override="compatible",
        save_json=False,
        dry_run=False,
        config_path=str(config_path),
    )

    assert raw["providers"]["compatible"]["provider_type"] == "openai"
    assert cfg.provider_routes["vision"].primary.model == "compatible-vision"
    assert cfg.provider_routes["translation"].primary.model == "compatible-text"


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


def test_build_project_config_preserves_ocr_guard_configuration(tmp_path):
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        '[stages.vision]\nprimary = "openai"\n\n'
        '[stages.translation]\nprimary = "gemini"\n\n'
        '[providers.openai]\napi_key = "openai-key"\nvision_model = "gpt-4o"\ntext_model = "gpt-4o-mini"\n\n'
        '[providers.gemini]\napi_key = "gemini-key"\nvision_model = "gemini-vision"\ntext_model = "gemini-text"\n\n'
        "[ocr_guard]\n"
        "enabled = true\n"
        "consecutive_blank_threshold = 3\n"
        'auto_recovery_strategy = "continue"\n',
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

    assert raw["ocr_guard"]["auto_recovery_strategy"] == "continue"
    assert cfg.ocr_guard == {
        "enabled": True,
        "consecutive_blank_threshold": 3,
        "auto_recovery_strategy": "continue",
    }
