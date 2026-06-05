from pathlib import Path

from PIL import Image

from mga.models.format import PageRef
from mga.runtime_bridge.external import _prepare_runtime_image_input


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
