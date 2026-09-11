import json
import asyncio
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image

from mga.models.format import PageRef
from mga.models import ProjectConfig, ProviderRoute, StageProviderConfig
from mga.runtime_bridge.external import (
    _complete_runtime_artifacts,
    _prepare_runtime_image_input,
    _resolve_runtime_openai_settings,
    run_export_artifact,
)


def test_prepare_runtime_image_input_expands_file_adapter_pages(tmp_path, monkeypatch):
    source_pages = tmp_path / "source-pages"
    source_pages.mkdir()
    for index in range(2):
        Image.new("RGB", (8, 8), "white").save(source_pages / f"src-{index}.png")

    class FakeAdapter:
        def extract(self, input_path: Path):
            assert input_path.name == "book.pdf"
            for index in range(2):
                yield PageRef(index=index, image_path=source_pages / f"src-{index}.png")

    monkeypatch.setattr("mga.format.get_adapter", lambda name: FakeAdapter())

    input_pdf = tmp_path / "book.pdf"
    input_pdf.write_bytes(b"%PDF")
    payload_dir = tmp_path / "payload"

    runtime_input = _prepare_runtime_image_input(input_pdf, payload_dir)

    assert runtime_input == payload_dir / ".runtime-input"
    assert sorted(path.name for path in runtime_input.iterdir()) == [
        "page-0000.png",
        "page-0001.png",
    ]
    manifest = json.loads((payload_dir / "runtime-input-manifest.json").read_text(encoding="utf-8"))
    assert manifest["input_suffix"] == ".pdf"
    assert manifest["pdf_render_dpi"] == 200
    assert manifest["page_count"] == 2


def test_run_export_artifact_writes_fast_export_config(tmp_path, monkeypatch):
    image = tmp_path / "page.png"
    Image.new("RGB", (8, 8), "white").save(image)
    payload_dir = tmp_path / "payload"
    model_dir = tmp_path / "models"
    monkeypatch.setenv("MANGA_TRANSLATOR_MODEL_DIR", str(model_dir))
    captured_command = []

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        captured_command.extend(command)
        payload_dir.joinpath("artifact.json").write_text("{}", encoding="utf-8")
        return Completed()

    monkeypatch.setattr("mga.runtime_bridge.external.subprocess.run", fake_run)

    run_export_artifact(input_dir=image, payload_dir=payload_dir)

    export_config = json.loads((payload_dir / "runtime-export-config.json").read_text(encoding="utf-8"))
    assert export_config["translator"]["translator"] == "none"
    assert export_config["inpainter"]["inpainter"] == "lama_large"
    assert export_config["inpainter"]["inpainting_size"] == 1024
    assert export_config["detector"]["detection_size"] == 1024
    assert captured_command[-2:] == ["--model-dir", str(model_dir)]


def test_run_export_artifact_fills_empty_page_when_runtime_skips_text(tmp_path, monkeypatch):
    image = tmp_path / "blank.png"
    Image.new("RGB", (8, 6), "white").save(image)
    payload_dir = tmp_path / "payload"

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr("mga.runtime_bridge.external.subprocess.run", lambda *args, **kwargs: Completed())

    run_export_artifact(input_dir=image, payload_dir=payload_dir)

    artifact = json.loads((payload_dir / "artifact-0000.json").read_text(encoding="utf-8"))
    assert artifact["text_regions"] == []
    assert artifact["image_shape"] == [6, 8, 3]
    assert (payload_dir / "inpainted-0000.png").exists()
    assert json.loads((payload_dir / "pages.json").read_text(encoding="utf-8")) == [
        {
            "page_index": 0,
            "artifact": "artifact-0000.json",
            "inpainted": "inpainted-0000.png",
        }
    ]


def test_runtime_empty_export_payload_consumes_page_slot(tmp_path):
    from manga_translator.config import Config
    from manga_translator.manga_translator import MangaTranslator
    from manga_translator.utils import Context

    payload_dir = tmp_path / "payload"
    with patch("manga_translator.manga_translator.MangaTranslator.__init__", return_value=None):
        translator = MangaTranslator()
    translator._export_artifact_dir = str(payload_dir)

    for expected_index in range(2):
        ctx = Context()
        ctx.img_rgb = np.ones((6, 8, 3), dtype=np.uint8) * 255
        translator._serialize_empty_render_payload_for_current_page(Config(), ctx)

        artifact = json.loads((payload_dir / f"artifact-{expected_index:04d}.json").read_text(encoding="utf-8"))
        assert artifact["page_index"] == expected_index
        assert artifact["text_regions"] == []
        assert artifact["image_shape"] == [6, 8, 3]
        assert (payload_dir / f"inpainted-{expected_index:04d}.png").exists()

    assert translator._export_page_counter == 2


def test_runtime_render_only_preserves_rgb_channel_order(tmp_path, monkeypatch):
    from manga_translator.config import Config
    from manga_translator.manga_translator import MangaTranslator

    payload_dir = tmp_path / "payload"
    payload_dir.mkdir()
    (payload_dir / "pages.json").write_text(
        json.dumps([{"page_index": 0, "artifact": "artifact-0000.json", "inpainted": "inpainted-0000.png"}]),
        encoding="utf-8",
    )
    (payload_dir / "artifact-0000.json").write_text(
        json.dumps({"version": 1, "page_index": 0, "text_regions": [], "image_shape": [2, 2, 3]}),
        encoding="utf-8",
    )
    Image.new("RGB", (2, 2), (200, 10, 30)).save(payload_dir / "inpainted-0000.png")

    with patch("manga_translator.manga_translator.MangaTranslator.__init__", return_value=None):
        translator = MangaTranslator()

    async def fake_render(config, ctx):
        return np.full((2, 2, 3), (200, 10, 30), dtype=np.uint8)

    monkeypatch.setattr(translator, "_run_text_rendering", fake_render)

    output_dir = tmp_path / "out"
    asyncio.run(translator.render_only(str(payload_dir), Config(), str(output_dir)))

    assert Image.open(output_dir / "page-001.png").convert("RGB").getpixel((0, 0)) == (200, 10, 30)


def test_run_export_artifact_clears_stale_artifacts_when_input_signature_changes(tmp_path, monkeypatch):
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    Image.new("RGB", (8, 6), "white").save(first)
    Image.new("RGB", (9, 7), "white").save(second)
    payload_dir = tmp_path / "payload"
    payload_dir.mkdir()
    (payload_dir / "runtime-input-manifest.json").write_text(
        json.dumps({"input_path": str(first.resolve())}) + "\n",
        encoding="utf-8",
    )
    (payload_dir / "artifact-0000.json").write_text('{"text_regions":[{"text":"stale"}]}', encoding="utf-8")
    (payload_dir / "inpainted-0000.png").write_bytes(b"stale")

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    monkeypatch.setattr("mga.runtime_bridge.external.subprocess.run", lambda *args, **kwargs: Completed())

    run_export_artifact(input_dir=second, payload_dir=payload_dir)

    artifact = json.loads((payload_dir / "artifact-0000.json").read_text(encoding="utf-8"))
    manifest = json.loads((payload_dir / "runtime-input-manifest.json").read_text(encoding="utf-8"))
    assert artifact["text_regions"] == []
    assert artifact["image_shape"] == [7, 9, 3]
    assert manifest["input_path"] == str(second.resolve())


def test_run_export_artifact_clears_stale_artifacts_even_when_manifest_matches(tmp_path, monkeypatch):
    image = tmp_path / "page.png"
    Image.new("RGB", (8, 6), "white").save(image)
    payload_dir = tmp_path / "payload"
    payload_dir.mkdir()

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        assert not (payload_dir / "artifact-0000.json").exists()
        return Completed()

    monkeypatch.setattr("mga.runtime_bridge.external.subprocess.run", fake_run)

    runtime_input = _prepare_runtime_image_input(image, payload_dir)
    assert runtime_input == image.resolve()
    (payload_dir / "artifact-0000.json").write_text('{"text_regions":[{"text":"stale"}]}', encoding="utf-8")
    (payload_dir / "inpainted-0000.png").write_bytes(b"stale")

    run_export_artifact(input_dir=image, payload_dir=payload_dir)

    artifact = json.loads((payload_dir / "artifact-0000.json").read_text(encoding="utf-8"))
    assert artifact["text_regions"] == []
    assert artifact["image_shape"] == [6, 8, 3]


def test_resolve_runtime_openai_settings_supports_compatible_provider_env(monkeypatch):
    monkeypatch.setenv("COMPATIBLE_API_KEY", "runtime-key")
    cfg = ProjectConfig(
        provider_routes={
            "translation": StageProviderConfig(
                primary=ProviderRoute(provider="compatible", model="route-model")
            )
        }
    )
    raw_config = {
        "providers": {
            "compatible": {
                "provider_type": "openai",
                "api_key_env": "COMPATIBLE_API_KEY",
                "base_url": "https://compatible.example/v1",
                "text_model": "compatible-text",
            }
        }
    }

    settings = _resolve_runtime_openai_settings(cfg, raw_config)

    assert settings["api_key"] == "runtime-key"
    assert settings["base_url"] == "https://compatible.example/v1"
    assert settings["text_model"] == "compatible-text"
    assert "api_key_env" not in settings


def test_resolve_runtime_openai_settings_uses_mimo_builtin_profile(monkeypatch):
    monkeypatch.setenv("MIMO_API_KEY", "runtime-mimo-key")
    cfg = ProjectConfig(
        provider_routes={
            "translation": StageProviderConfig(primary=ProviderRoute(provider="mimo"))
        }
    )

    settings = _resolve_runtime_openai_settings(cfg, {"providers": {"mimo": {}}})

    assert settings["api_key"] == "runtime-mimo-key"
    assert settings["base_url"] == "https://token-plan-cn.xiaomimimo.com/v1"
    assert settings["text_model"] == "mimo-v2.5-pro"
