"""Tests for CLI novel mode."""

import importlib
from pathlib import Path

from click.testing import CliRunner

from mga.models import Page, PageImage
from mga.cli.main import _detect_mode, translate
from mga.pipeline.stages import PipelineContext


def _setup_config(tmp_path: Path, monkeypatch) -> Path:
    """Create minimal provider config and set env var."""
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        '[stages.vision]\nprimary = "openai"\n\n'
        '[stages.translation]\nprimary = "openai"\n\n'
        '[providers.openai]\napi_key = "test-key"\nvision_model = "gpt-4o"\ntext_model = "gpt-4o-mini"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("MANGA_TRANSLATE_CONFIG", str(config_path))
    return config_path


def _setup_multi_provider_config(tmp_path: Path, monkeypatch) -> Path:
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        '[stages.vision]\nprimary = "openai"\n\n'
        '[stages.translation]\nprimary = "openai"\n\n'
        '[providers.openai]\napi_key = "test-key"\nvision_model = "gpt-4o"\ntext_model = "gpt-4o-mini"\n\n'
        '[providers.gemini]\napi_key = "gemini-key"\nvision_model = "gemini-vision"\ntext_model = "gemini-text"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("MANGA_TRANSLATE_CONFIG", str(config_path))
    return config_path


def test_detect_mode_auto_txt():
    mode, fmt = _detect_mode("chapter.txt", None)
    assert mode == "novel"
    assert fmt == "txt"


def test_detect_mode_auto_epub():
    mode, fmt = _detect_mode("book.epub", None)
    assert mode == "novel"
    assert fmt == "epub"


def test_detect_mode_auto_mobi():
    mode, fmt = _detect_mode("book.mobi", None)
    assert mode == "novel"
    assert fmt == "mobi"


def test_detect_mode_auto_images_dir():
    mode, fmt = _detect_mode("pages/", None)
    assert mode == "manga"
    assert fmt == "images"


def test_detect_mode_explicit_novel():
    mode, fmt = _detect_mode("something.png", "novel")
    assert mode == "novel"
    assert fmt == "png"


def test_detect_mode_explicit_manga():
    mode, fmt = _detect_mode("book.epub", "manga")
    assert mode == "manga"
    assert fmt == "images"


def test_translate_novel_mode_dry_run(tmp_path, monkeypatch):
    """Test --mode novel --dry-run."""
    _setup_config(tmp_path, monkeypatch)
    txt = tmp_path / "test.txt"
    txt.write_text("Hello world", encoding="utf-8")
    output = tmp_path / "out.txt"

    runner = CliRunner()
    result = runner.invoke(translate, [
        str(txt), "-o", str(output),
        "--mode", "novel", "--dry-run", "--lang", "en-zh",
    ])
    assert result.exit_code == 0, result.output
    assert "novel" in result.output.lower() or "Dry run" in result.output


def test_translate_auto_detect_novel_dry_run(tmp_path, monkeypatch):
    """Test auto-detection of novel mode from .txt extension."""
    _setup_config(tmp_path, monkeypatch)
    txt = tmp_path / "chapter.txt"
    txt.write_text("Hello world", encoding="utf-8")
    output = tmp_path / "out.txt"

    runner = CliRunner()
    result = runner.invoke(translate, [
        str(txt), "-o", str(output),
        "--dry-run", "--lang", "en-zh",
    ])
    assert result.exit_code == 0, result.output
    assert "novel" in result.output.lower() or "Dry run" in result.output


def test_translate_provider_override_accepts_any_configured_provider(tmp_path, monkeypatch):
    _setup_multi_provider_config(tmp_path, monkeypatch)
    txt = tmp_path / "chapter.txt"
    txt.write_text("Hello world", encoding="utf-8")
    output = tmp_path / "out.txt"

    runner = CliRunner()
    result = runner.invoke(translate, [
        str(txt), "-o", str(output),
        "--mode", "novel", "--dry-run", "--provider", "gemini",
    ])

    assert result.exit_code == 0, result.output
    assert '"provider": "gemini"' in result.output
    assert '"model": "gemini-text"' in result.output


def test_translate_learn_only_seeds_memory_with_configured_learning_provider(tmp_path, monkeypatch):
    """--learn-only should seed memory with the configured provider and skip translation."""
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        '[stages.vision]\nprimary = "openai"\n\n'
        '[stages.translation]\nprimary = "gemini"\n\n'
        '[providers.openai]\napi_key = "vision-key"\nvision_model = "gpt-4o"\ntext_model = "gpt-4o-mini"\n\n'
        '[providers.gemini]\napi_key = "learning-key"\nvision_model = "gemini-vision"\ntext_model = "gemini-text"\n',
        encoding="utf-8",
    )
    txt = tmp_path / "chapter.txt"
    txt.write_text("Hello world", encoding="utf-8")
    learn_dir = tmp_path / "learned_examples"
    learn_dir.mkdir()
    output = tmp_path / "out.txt"
    provider_instance = object()
    captured = {}

    def fake_get_provider(name, **settings):
        captured["provider_name"] = name
        captured["provider_settings"] = settings
        return provider_instance

    class FakeLearningResult:
        characters = []
        terms = []

    class FakeLearningEngine:
        def __init__(self, project_dir, provider=None):
            captured["learning_project_dir"] = project_dir
            captured["learning_provider"] = provider

        def learn(self, learn_from, mode="auto"):
            captured["learn_from"] = learn_from
            captured["learn_mode"] = mode
            return FakeLearningResult()

    class FailingOrchestrator:
        def __init__(self, *args, **kwargs):
            raise AssertionError("PipelineOrchestrator should not be instantiated")

    monkeypatch.setattr("mga.providers.get_provider", fake_get_provider)
    monkeypatch.setattr("mga.learning.engine.LearningEngine", FakeLearningEngine)
    monkeypatch.setattr("mga.pipeline.orchestrator.PipelineOrchestrator", FailingOrchestrator)

    runner = CliRunner()
    result = runner.invoke(translate, [
        str(txt), "-o", str(output),
        "--config", str(config_path),
        "--learn-from", str(learn_dir),
        "--learn-only",
        "--lang", "ja-zh",
    ])

    assert result.exit_code == 0, result.output
    assert captured["provider_name"] == "gemini"
    assert captured["provider_settings"]["api_key"] == "learning-key"
    assert captured["provider_settings"]["text_model"] == "gemini-text"
    assert captured["learning_provider"] is provider_instance
    assert captured["learn_from"] == learn_dir
    assert captured["learn_mode"] == "novel"
    assert "Memory seeded. --learn-only set, skipping translation." in result.output


def test_translate_manga_runs_intelligence_pipeline_after_runtime_export(tmp_path, monkeypatch):
    """Manga CLI should pass runtime artifacts into the mga pipeline, not stop at external-core."""
    _setup_config(tmp_path, monkeypatch)
    input_dir = tmp_path / "pages"
    input_dir.mkdir()
    (input_dir / "page-0001.png").write_bytes(b"fake")
    output_dir = tmp_path / "out"
    payload_dir = output_dir / ".mga-payload"
    captured = {}

    def fake_precheck(cfg):
        captured["precheck_pipeline_mode"] = cfg.pipeline_mode

    def fake_export(input_dir, payload_dir):
        payload_dir.mkdir(parents=True)
        captured["export_input_dir"] = input_dir
        captured["export_payload_dir"] = payload_dir

    class FakeOrchestrator:
        def __init__(self, config=None):
            captured["orchestrator_config"] = config

        def run(self, input_path, output_path, cfg, metadata=None):
            captured["run_input_path"] = input_path
            captured["run_output_path"] = output_path
            captured["run_cfg"] = cfg
            captured["run_metadata"] = metadata
            return PipelineContext(
                project_config=cfg,
                pages=[Page(page_id="page_0000", page_index=0, image=PageImage(path=str(input_dir / "page-0001.png")))],
            )

    cli_main = importlib.import_module("mga.cli.main")
    monkeypatch.setattr(cli_main, "_check_translation_provider_connectivity", fake_precheck)
    monkeypatch.setattr("mga.runtime_bridge.external.run_export_artifact", fake_export)
    monkeypatch.setattr("mga.pipeline.orchestrator.PipelineOrchestrator", FakeOrchestrator)

    runner = CliRunner()
    result = runner.invoke(translate, [str(input_dir), "-o", str(output_dir), "--lang", "ja-zh"])

    assert result.exit_code == 0, result.output
    assert captured["precheck_pipeline_mode"] == "manga"
    assert captured["export_input_dir"] == input_dir
    assert captured["export_payload_dir"] == payload_dir
    assert captured["run_metadata"] == {"artifact_payload_dir": str(payload_dir)}
    assert captured["run_cfg"].pipeline_mode == "manga"
