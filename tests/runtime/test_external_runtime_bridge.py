import json
from pathlib import Path

from PIL import Image

from mga.models.format import PageRef
from mga.runtime_bridge.external import _prepare_runtime_image_input, run_export_artifact


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


def test_run_export_artifact_writes_fast_export_config(tmp_path, monkeypatch):
    image = tmp_path / "page.png"
    Image.new("RGB", (8, 8), "white").save(image)
    payload_dir = tmp_path / "payload"

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(command, **kwargs):
        payload_dir.joinpath("artifact.json").write_text("{}", encoding="utf-8")
        return Completed()

    monkeypatch.setattr("mga.runtime_bridge.external.subprocess.run", fake_run)

    run_export_artifact(input_dir=image, payload_dir=payload_dir)

    export_config = json.loads((payload_dir / "runtime-export-config.json").read_text(encoding="utf-8"))
    assert export_config["translator"]["translator"] == "none"
    assert export_config["inpainter"]["inpainter"] == "none"
    assert export_config["inpainter"]["inpainting_size"] == 1024
    assert export_config["detector"]["detection_size"] == 1024


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
