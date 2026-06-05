from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from manga_translate.cli import main
from mga.cli.main import main as mga_main
from mga.cli.main import _resolve_stage_provider
from mga.models import ProjectConfig, ProviderRoute, StageProviderConfig


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


def test_mga_legacy_benchmark_extraction_falls_back_when_primary_provider_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "001.png").write_bytes(b"fake image data")
    output_dir = tmp_path / "output"
    config_path = tmp_path / "providers.toml"
    config_path.write_text(
        '[stages.vision]\nprimary = "openai"\nfallback = "gemini"\n\n'
        '[stages.translation]\nprimary = "openai"\n\n'
        '[stages.qa]\nprimary = "openai"\n\n'
        '[providers.openai]\napi_key = "bad-key"\nvision_model = "bad-vision"\ntext_model = "bad-text"\n\n'
        '[providers.gemini]\napi_key = "good-key"\nvision_model = "good-vision"\ntext_model = "good-text"\n',
        encoding="utf-8",
    )
    provider_instance = object()
    captured = {"providers": []}

    def fake_get_provider(name, **settings):
        captured["providers"].append((name, settings))
        if name == "openai":
            raise RuntimeError("primary unavailable")
        return provider_instance

    def fake_run_extraction_benchmark(**kwargs):
        captured["benchmark_provider"] = kwargs["provider"]
        captured["ocr_specs"] = kwargs["ocr_specs"]
        return {"page_count": len(kwargs["pages"])}

    monkeypatch.setattr("mga.providers.get_provider", fake_get_provider)
    monkeypatch.setattr("mga.benchmark.evaluate.run_extraction_benchmark", fake_run_extraction_benchmark)

    result = runner.invoke(
        mga_main,
        [
            "legacy",
            "benchmark-extraction",
            str(input_dir),
            "-o",
            str(output_dir),
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert [name for name, _settings in captured["providers"]] == ["openai", "gemini"]
    assert captured["providers"][1][1]["api_key"] == "good-key"
    assert captured["providers"][1][1]["model"] == "good-vision"
    assert captured["benchmark_provider"] is provider_instance
    assert captured["ocr_specs"] == ["tesseract_jpn"]


def test_mga_stage_provider_falls_back_for_benchmark_runtime_methods(monkeypatch) -> None:
    captured = {"providers": []}

    class BrokenProvider:
        def vision_extract(self, *args, **kwargs):
            raise RuntimeError("primary runtime down")

    class WorkingProvider:
        def vision_extract(self, *args, **kwargs):
            return ("page", "trace")

    def fake_get_provider(name, **settings):
        captured["providers"].append((name, settings))
        return BrokenProvider() if name == "openai" else WorkingProvider()

    monkeypatch.setattr("mga.providers.get_provider", fake_get_provider)
    cfg = ProjectConfig(
        provider_routes={
            "vision": StageProviderConfig(
                primary=ProviderRoute(provider="openai", model="primary-vision"),
                fallback=ProviderRoute(provider="gemini", model="fallback-vision"),
            )
        },
        provider_settings={
            "openai": {"api_key": "primary-key"},
            "gemini": {"api_key": "fallback-key"},
        },
    )

    provider = _resolve_stage_provider(cfg, "vision")

    assert provider.vision_extract("page", store="store") == ("page", "trace")
    assert [name for name, _settings in captured["providers"]] == ["openai", "gemini"]
    assert captured["providers"][0][1]["model"] == "primary-vision"
    assert captured["providers"][1][1]["model"] == "fallback-vision"


def test_compat_legacy_benchmark_extraction_builds_fallback_provider_from_raw_config(
    monkeypatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    (input_dir / "001.png").write_bytes(b"fake image data")
    output_dir = tmp_path / "output"
    provider_instance = object()
    captured = {"provider_names": []}

    monkeypatch.setattr(
        "manga_translate.cli.build_project_config",
        lambda **kwargs: (
            type("ProjectConfigStub", (), {"output_dir": str(output_dir)})(),
            {
                "stages": {"vision": {"primary": "openai", "fallback": "gemini"}},
                "providers": {
                    "openai": {"api_key": "bad-key"},
                    "gemini": {"api_key": "good-key"},
                },
            },
        ),
    )
    monkeypatch.setattr(
        "manga_translate.cli.ingest_pages",
        lambda project_config, store: ([type("PageStub", (), {"page_id": "page-0001"})()], None),
    )

    def fake_get_provider(name, **settings):
        captured["provider_names"].append(name)
        if name == "openai":
            raise RuntimeError("primary unavailable")
        captured["fallback_settings"] = settings
        return provider_instance

    def fake_run_extraction_benchmark(**kwargs):
        captured["benchmark_provider"] = kwargs["provider"]
        captured["ocr_specs"] = kwargs["ocr_specs"]
        return {"page_count": len(kwargs["pages"])}

    monkeypatch.setattr("mga.providers.get_provider", fake_get_provider)
    monkeypatch.setattr("manga_translate.cli.run_extraction_benchmark", fake_run_extraction_benchmark)

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

    assert result.exit_code == 0, result.output
    assert captured["provider_names"] == ["openai", "gemini"]
    assert captured["fallback_settings"]["api_key"] == "good-key"
    assert captured["benchmark_provider"] is provider_instance
    assert captured["ocr_specs"] == ["tesseract_jpn"]


def test_compat_legacy_provider_falls_back_for_runtime_vision_extract(monkeypatch) -> None:
    from manga_translate.cli import build_legacy_provider

    captured = {"providers": []}
    raw_config = {
        "stages": {"vision": {"primary": "openai", "fallback": "gemini"}},
        "providers": {
            "openai": {"api_key": "primary-key"},
            "gemini": {"api_key": "fallback-key"},
        },
    }

    class BrokenProvider:
        def vision_extract(self, *args, **kwargs):
            raise RuntimeError("primary runtime down")

    class WorkingProvider:
        def vision_extract(self, *args, **kwargs):
            return ("page", "trace")

    def fake_get_provider(name, **settings):
        captured["providers"].append((name, settings))
        return BrokenProvider() if name == "openai" else WorkingProvider()

    monkeypatch.setattr("mga.providers.get_provider", fake_get_provider)

    provider = build_legacy_provider(raw_config, None, stage="vision")

    assert provider.vision_extract("page", store="store") == ("page", "trace")
    assert [name for name, _settings in captured["providers"]] == ["openai", "gemini"]


def test_compat_legacy_provider_falls_back_for_runtime_translation_methods(monkeypatch) -> None:
    from manga_translate.cli import build_legacy_provider

    captured = {"providers": []}
    raw_config = {
        "stages": {"translation": {"primary": "openai", "fallback": "gemini"}},
        "providers": {
            "openai": {"api_key": "primary-key"},
            "gemini": {"api_key": "fallback-key"},
        },
    }

    class BrokenProvider:
        def translate(self, *args, **kwargs):
            raise RuntimeError("primary translate down")

        def direct_translate_page(self, *args, **kwargs):
            raise RuntimeError("primary direct down")

    class WorkingProvider:
        def translate(self, *args, **kwargs):
            return (["translated"], "trace")

        def direct_translate_page(self, *args, **kwargs):
            return (["direct"], "trace")

    def fake_get_provider(name, **settings):
        captured["providers"].append((name, settings))
        return BrokenProvider() if name == "openai" else WorkingProvider()

    monkeypatch.setattr("mga.providers.get_provider", fake_get_provider)

    provider = build_legacy_provider(raw_config, None, stage="translation")

    assert provider.translate("page", ["utterance"], store="store") == (["translated"], "trace")
    assert provider.direct_translate_page("page", store="store") == (["direct"], "trace")
    assert [name for name, _settings in captured["providers"]] == ["openai", "gemini"]
