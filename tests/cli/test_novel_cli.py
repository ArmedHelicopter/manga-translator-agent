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


def test_detect_mode_auto_pdf():
    mode, fmt = _detect_mode("book.pdf", None)
    assert mode == "manga"
    assert fmt == "pdf"


def test_detect_mode_auto_cbz():
    mode, fmt = _detect_mode("chapter.cbz", None)
    assert mode == "manga"
    assert fmt == "cbz"


def test_detect_mode_explicit_novel():
    mode, fmt = _detect_mode("something.png", "novel")
    assert mode == "novel"
    assert fmt == "png"


def test_detect_mode_explicit_manga():
    mode, fmt = _detect_mode("book.epub", "manga")
    assert mode == "manga"
    assert fmt == "epub"


def test_detect_mode_explicit_manga_mobi():
    mode, fmt = _detect_mode("book.mobi", "manga")
    assert mode == "manga"
    assert fmt == "mobi"


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


def test_translate_verbose_flag_is_accepted_in_product_cli(tmp_path, monkeypatch):
    _setup_config(tmp_path, monkeypatch)
    txt = tmp_path / "chapter.txt"
    txt.write_text("Hello world", encoding="utf-8")
    output = tmp_path / "out.txt"

    runner = CliRunner()
    result = runner.invoke(translate, [
        str(txt), "-o", str(output),
        "-v", "--dry-run", "--lang", "en-zh",
    ])

    assert result.exit_code == 0, result.output
    assert "Dry run" in result.output


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


def test_translate_learn_only_falls_back_when_primary_learning_provider_fails(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        '[stages.vision]\nprimary = "openai"\n\n'
        '[stages.translation]\nprimary = "openai"\nfallback = "gemini"\n\n'
        '[providers.openai]\napi_key = "bad-key"\nvision_model = "gpt-4o"\ntext_model = "gpt-4o-mini"\n\n'
        '[providers.gemini]\napi_key = "learning-key"\ntext_model = "gemini-text"\n',
        encoding="utf-8",
    )
    txt = tmp_path / "chapter.txt"
    txt.write_text("Hello world", encoding="utf-8")
    learn_dir = tmp_path / "learned_examples"
    learn_dir.mkdir()
    output = tmp_path / "out.txt"
    provider_instance = object()
    captured = {"provider_names": []}

    def fake_get_provider(name, **settings):
        captured["provider_names"].append(name)
        if name == "openai":
            raise RuntimeError("primary unavailable")
        captured["provider_settings"] = settings
        return provider_instance

    class FakeLearningResult:
        characters = []
        terms = []

    class FakeLearningEngine:
        def __init__(self, project_dir, provider=None):
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
    assert captured["provider_names"] == ["openai", "gemini"]
    assert captured["provider_settings"]["api_key"] == "learning-key"
    assert captured["provider_settings"]["text_model"] == "gemini-text"
    assert captured["learning_provider"] is provider_instance
    assert captured["learn_from"] == learn_dir
    assert captured["learn_mode"] == "novel"


def test_translate_learn_only_runtime_provider_call_falls_back_to_secondary(
    tmp_path,
    monkeypatch,
):
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        '[stages.vision]\nprimary = "openai"\n\n'
        '[stages.translation]\nprimary = "openai"\nfallback = "gemini"\n\n'
        '[providers.openai]\napi_key = "primary-key"\ntext_model = "primary-text"\nvision_model = "primary-vision"\n\n'
        '[providers.gemini]\napi_key = "fallback-key"\ntext_model = "fallback-text"\n',
        encoding="utf-8",
    )
    txt = tmp_path / "chapter.txt"
    txt.write_text("Hello world", encoding="utf-8")
    learn_dir = tmp_path / "learned_examples"
    learn_dir.mkdir()
    output = tmp_path / "out.txt"
    captured = {"provider_names": []}

    class BrokenProvider:
        def chat_structured(self, **kwargs):
            raise RuntimeError("primary runtime unavailable")

    class WorkingProvider:
        def chat_structured(self, **kwargs):
            captured["fallback_schema"] = kwargs["schema"]
            return {"ok": True}

    def fake_get_provider(name, **settings):
        captured["provider_names"].append(name)
        if name == "openai":
            return BrokenProvider()
        captured["fallback_settings"] = settings
        return WorkingProvider()

    class FakeLearningResult:
        characters = []
        terms = []

    class FakeLearningEngine:
        def __init__(self, project_dir, provider=None):
            captured["learning_provider"] = provider

        def learn(self, learn_from, mode="auto"):
            captured["runtime_result"] = captured["learning_provider"].chat_structured(
                messages=[{"role": "user", "content": "x"}],
                schema={"type": "object"},
            )
            captured["provider_errors"] = captured["learning_provider"].errors
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
    assert captured["provider_names"] == ["openai", "gemini"]
    assert captured["fallback_settings"]["api_key"] == "fallback-key"
    assert captured["runtime_result"] == {"ok": True}
    assert captured["provider_errors"][0]["provider"] == "openai"


def test_translate_learn_only_uses_input_path_when_learn_from_is_omitted(tmp_path, monkeypatch):
    _setup_config(tmp_path, monkeypatch)
    input_dir = tmp_path / "pages"
    input_dir.mkdir()
    (input_dir / "page-0001.png").write_bytes(b"fake")
    output = tmp_path / "out"
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
            captured["learning_project_dir"] = Path(project_dir)
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
        str(input_dir), "-o", str(output),
        "--learn-only",
        "--lang", "ja-zh",
    ])

    assert result.exit_code == 0, result.output
    assert captured["provider_name"] == "openai"
    assert captured["learning_provider"] is provider_instance
    assert captured["learning_project_dir"] == input_dir.resolve()
    assert captured["learn_from"] == input_dir
    assert captured["learn_mode"] == "manga"
    assert "Memory seeded. --learn-only set, skipping translation." in result.output


def test_translate_learn_only_output_profiles_exports_generated_toml(tmp_path, monkeypatch):
    _setup_config(tmp_path, monkeypatch)
    input_dir = tmp_path / "pages"
    input_dir.mkdir()
    (input_dir / "page-0001.png").write_bytes(b"fake")
    output_dir = tmp_path / "out"
    profiles_dir = tmp_path / "profiles"
    provider_instance = object()
    captured = {}

    def fake_get_provider(name, **settings):
        captured["provider_name"] = name
        return provider_instance

    class FakeLearningResult:
        characters = [{"character_id": "akari"}]
        terms = []

    class FakeLearningEngine:
        def __init__(self, project_dir, provider=None):
            captured["learning_project_dir"] = Path(project_dir)

        def learn(self, learn_from, mode="auto"):
            captured["learn_from"] = learn_from
            generated_dir = captured["learning_project_dir"] / "character_profiles"
            generated_dir.mkdir(parents=True, exist_ok=True)
            (generated_dir / "akari.toml").write_text(
                '[meta]\ncharacter_id = "akari"\nname_jp = "Akari"\n',
                encoding="utf-8",
            )
            return FakeLearningResult()

    class FailingOrchestrator:
        def __init__(self, *args, **kwargs):
            raise AssertionError("PipelineOrchestrator should not be instantiated")

    monkeypatch.setattr("mga.learning.engine.LearningEngine", FakeLearningEngine)
    monkeypatch.setattr("mga.providers.get_provider", fake_get_provider)
    monkeypatch.setattr("mga.pipeline.orchestrator.PipelineOrchestrator", FailingOrchestrator)

    runner = CliRunner()
    result = runner.invoke(translate, [
        str(input_dir), "-o", str(output_dir),
        "--learn-only",
        "--output-profiles", str(profiles_dir),
        "--lang", "ja-zh",
    ])

    assert result.exit_code == 0, result.output
    assert captured["provider_name"] == "openai"
    assert captured["learn_from"] == input_dir
    assert (profiles_dir / "akari.toml").read_text(encoding="utf-8").startswith("[meta]")
    assert "Profiles exported: 1 profiles" in result.output
    assert "Memory seeded. --learn-only set, skipping translation." in result.output


def test_translate_manga_learn_from_seeds_persona_before_pipeline(tmp_path, monkeypatch):
    """--learn-from should seed persona artifacts before normal manga translation."""
    _setup_config(tmp_path, monkeypatch)
    input_dir = tmp_path / "pages"
    input_dir.mkdir()
    (input_dir / "page-0001.png").write_bytes(b"fake")
    learn_dir = tmp_path / "learned_examples"
    learn_dir.mkdir()
    output_dir = tmp_path / "out"
    payload_dir = output_dir / ".mga-payload"
    provider_instance = object()
    captured = {}

    def fake_get_provider(name, **settings):
        captured["learning_provider_name"] = name
        captured["learning_provider_settings"] = settings
        return provider_instance

    class FakeLearningResult:
        characters = [{"character_id": "akari"}]
        terms = []

    class FakeLearningEngine:
        def __init__(self, project_dir, provider=None):
            captured["learning_project_dir"] = Path(project_dir)
            captured["learning_provider"] = provider

        def learn(self, learn_from, mode="auto"):
            captured["learn_from"] = learn_from
            captured["learn_mode"] = mode
            profiles_dir = captured["learning_project_dir"] / "character_profiles"
            profiles_dir.mkdir(parents=True, exist_ok=True)
            (profiles_dir / "akari.toml").write_text(
                '[meta]\ncharacter_id = "akari"\nname_jp = "Akari"\n',
                encoding="utf-8",
            )
            return FakeLearningResult()

    def fake_precheck(cfg):
        captured["precheck_after_learning"] = (
            Path(cfg.working_dir) / "character_profiles" / "akari.toml"
        ).exists()

    def fake_export(input_dir, payload_dir):
        payload_dir.mkdir(parents=True)
        captured["export_after_learning"] = (
            Path(input_dir).resolve() / "character_profiles" / "akari.toml"
        ).exists()

    class FailingOrchestrator:
        def __init__(self, *args, **kwargs):
            raise AssertionError("PipelineOrchestrator should not be instantiated directly")

    class FakeIncrementalTranslator:
        def __init__(self, project_dir, config=None):
            captured["incremental_project_dir"] = project_dir
            captured["incremental_config"] = config

        def translate_chapter(self, input_path, output_path, chapter_id="", metadata=None):
            profile_path = Path(captured["incremental_config"].working_dir) / "character_profiles" / "akari.toml"
            captured["pipeline_saw_profile"] = profile_path.exists()
            captured["pipeline_metadata"] = metadata
            captured["chapter_id"] = chapter_id
            return PipelineContext(project_config=captured["incremental_config"])

    cli_main = importlib.import_module("mga.cli.main")
    monkeypatch.setattr("mga.providers.get_provider", fake_get_provider)
    monkeypatch.setattr("mga.learning.engine.LearningEngine", FakeLearningEngine)
    monkeypatch.setattr(cli_main, "_check_translation_provider_connectivity", fake_precheck)
    monkeypatch.setattr(cli_main, "_check_vision_provider_capability", lambda cfg, auto_vision_model=False: None)
    monkeypatch.setattr("mga.runtime_bridge.external.run_export_artifact", fake_export)
    monkeypatch.setattr("mga.pipeline.orchestrator.PipelineOrchestrator", FailingOrchestrator)
    monkeypatch.setattr("mga.pipeline.incremental.IncrementalTranslator", FakeIncrementalTranslator)

    runner = CliRunner()
    result = runner.invoke(
        translate,
        [
            str(input_dir),
            "-o",
            str(output_dir),
            "--learn-from",
            str(learn_dir),
            "--lang",
            "ja-zh",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["learning_provider_name"] == "openai"
    assert captured["learning_provider"] is provider_instance
    assert captured["learn_from"] == learn_dir
    assert captured["learn_mode"] == "manga"
    assert captured["learning_project_dir"] == input_dir.resolve()
    assert captured["precheck_after_learning"] is True
    assert captured["export_after_learning"] is True
    assert captured["incremental_project_dir"] == input_dir.resolve()
    assert captured["pipeline_saw_profile"] is True
    assert captured["pipeline_metadata"] == {"artifact_payload_dir": str(payload_dir)}
    assert captured["chapter_id"] == input_dir.name
    assert "Learning complete: 1 characters, 0 terms" in result.output


def test_translate_manga_defaults_to_incremental_after_runtime_export(tmp_path, monkeypatch):
    """Manga CLI should use incremental translation by default after runtime export."""
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

    class FailingOrchestrator:
        def __init__(self, *args, **kwargs):
            raise AssertionError("PipelineOrchestrator should not be instantiated directly")

    class FakeIncrementalTranslator:
        def __init__(self, project_dir, config=None):
            captured["incremental_project_dir"] = project_dir
            captured["incremental_config"] = config

        def translate_chapter(self, input_path, output_path, chapter_id="", metadata=None):
            captured["incremental_input_path"] = input_path
            captured["incremental_output_path"] = output_path
            captured["chapter_id"] = chapter_id
            captured["metadata"] = metadata
            return PipelineContext(project_config=captured["incremental_config"])

    cli_main = importlib.import_module("mga.cli.main")
    monkeypatch.setattr(cli_main, "_check_translation_provider_connectivity", fake_precheck)
    monkeypatch.setattr(cli_main, "_check_vision_provider_capability", lambda cfg, auto_vision_model=False: None)
    monkeypatch.setattr("mga.runtime_bridge.external.run_export_artifact", fake_export)
    monkeypatch.setattr("mga.pipeline.orchestrator.PipelineOrchestrator", FailingOrchestrator)
    monkeypatch.setattr("mga.pipeline.incremental.IncrementalTranslator", FakeIncrementalTranslator)

    runner = CliRunner()
    result = runner.invoke(translate, [str(input_dir), "-o", str(output_dir), "--lang", "ja-zh"])

    assert result.exit_code == 0, result.output
    assert captured["precheck_pipeline_mode"] == "manga"
    assert captured["export_input_dir"] == input_dir
    assert captured["export_payload_dir"] == payload_dir
    assert captured["incremental_project_dir"] == input_dir.resolve()
    assert captured["incremental_config"].pipeline_mode == "manga"
    assert captured["incremental_input_path"] == str(input_dir)
    assert captured["incremental_output_path"] == str(output_dir)
    assert captured["chapter_id"] == input_dir.name
    assert captured["metadata"] == {"artifact_payload_dir": str(payload_dir)}
    assert f"Incremental translation complete: {input_dir.name}" in result.output


def test_translate_manga_incremental_uses_incremental_translator_after_runtime_export(tmp_path, monkeypatch):
    """--incremental should keep the manga runtime payload path and use IncrementalTranslator."""
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

    class FailingOrchestrator:
        def __init__(self, *args, **kwargs):
            raise AssertionError("PipelineOrchestrator should not be instantiated directly")

    class FakeIncrementalTranslator:
        def __init__(self, project_dir, config=None):
            captured["incremental_project_dir"] = project_dir
            captured["incremental_config"] = config

        def translate_chapter(self, input_path, output_path, chapter_id="", metadata=None):
            captured["incremental_input_path"] = input_path
            captured["incremental_output_path"] = output_path
            captured["chapter_id"] = chapter_id
            captured["metadata"] = metadata
            return PipelineContext(project_config=captured["incremental_config"])

    cli_main = importlib.import_module("mga.cli.main")
    monkeypatch.setattr(cli_main, "_check_translation_provider_connectivity", fake_precheck)
    monkeypatch.setattr(cli_main, "_check_vision_provider_capability", lambda cfg, auto_vision_model=False: None)
    monkeypatch.setattr("mga.runtime_bridge.external.run_export_artifact", fake_export)
    monkeypatch.setattr("mga.pipeline.orchestrator.PipelineOrchestrator", FailingOrchestrator)
    monkeypatch.setattr("mga.pipeline.incremental.IncrementalTranslator", FakeIncrementalTranslator)

    runner = CliRunner()
    result = runner.invoke(
        translate,
        [
            str(input_dir),
            "-o",
            str(output_dir),
            "--lang",
            "ja-zh",
            "--incremental",
            "--chapter-id",
            "ch011",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["precheck_pipeline_mode"] == "manga"
    assert captured["export_input_dir"] == input_dir
    assert captured["export_payload_dir"] == payload_dir
    assert captured["incremental_project_dir"] == input_dir.resolve()
    assert captured["incremental_config"].pipeline_mode == "manga"
    assert captured["incremental_input_path"] == str(input_dir)
    assert captured["incremental_output_path"] == str(output_dir)
    assert captured["chapter_id"] == "ch011"
    assert captured["metadata"] == {"artifact_payload_dir": str(payload_dir)}
    assert "Incremental translation complete: ch011" in result.output
