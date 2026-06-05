"""Tests for PDF adapter dependency handling and fitz protocol."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mga.format.pdf_adapter import PDFAdapter, _get_fitz
from mga.models import TranslatedPage


def test_get_fitz_raises_clear_install_message_when_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "fitz", None)

    with pytest.raises(ImportError, match="PyMuPDF is required for PDF support"):
        _get_fitz()


def _fake_fitz_module():
    class FakePixmap:
        def __init__(self, index: int) -> None:
            self.index = index

        def save(self, path: str) -> None:
            Path(path).write_bytes(f"page-{self.index}".encode("ascii"))

    class FakeSourcePage:
        def __init__(self, index: int) -> None:
            self.index = index

        def get_pixmap(self, matrix, alpha: bool):
            assert matrix == ("matrix", 200 / 72.0, 200 / 72.0)
            assert alpha is False
            return FakePixmap(self.index)

    class FakeSourcePDF:
        page_count = 2

        def load_page(self, index: int):
            return FakeSourcePage(index)

        def close(self) -> None:
            pass

    class FakeImageDoc:
        def __init__(self, path) -> None:
            self.path = Path(path)

        def __getitem__(self, index: int):
            assert index == 0
            return SimpleNamespace(rect=SimpleNamespace(width=100, height=200))

        def convert_to_pdf(self) -> bytes:
            return self.path.name.encode("ascii")

        def close(self) -> None:
            pass

    class FakeEmbeddedPDF:
        def __init__(self, payload: bytes) -> None:
            self.payload = payload

        def close(self) -> None:
            pass

    class FakeOutputPage:
        def __init__(self, owner) -> None:
            self.owner = owner

        def show_pdf_page(self, rect, pdf_page_doc, page_number: int) -> None:
            assert rect == ("rect", 0, 0, 100, 200)
            assert page_number == 0
            self.owner.inserted.append(pdf_page_doc.payload)

    class FakeOutputPDF:
        def __init__(self) -> None:
            self.inserted: list[bytes] = []

        def new_page(self, *, width: float, height: float):
            assert (width, height) == (100, 200)
            return FakeOutputPage(self)

        def save(self, path: str) -> None:
            Path(path).write_bytes(b"|".join(self.inserted))

        def close(self) -> None:
            pass

    def fake_open(*args):
        if not args:
            return FakeOutputPDF()
        if args[0] == "pdf":
            return FakeEmbeddedPDF(args[1])
        path = Path(args[0])
        if path.suffix.lower() == ".pdf":
            return FakeSourcePDF()
        return FakeImageDoc(path)

    return SimpleNamespace(
        open=fake_open,
        Matrix=lambda x, y: ("matrix", x, y),
        Rect=lambda x0, y0, x1, y1: ("rect", x0, y0, x1, y1),
    )


def test_pdf_adapter_extract_uses_fitz_and_preserves_metadata(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "fitz", _fake_fitz_module())
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"%PDF")

    pages = list(PDFAdapter().extract(pdf_path))

    assert [page.index for page in pages] == [0, 1]
    assert [page.original_ref for page in pages] == [
        "book.pdf#page=0",
        "book.pdf#page=1",
    ]
    assert [Path(page.image_path).read_bytes() for page in pages] == [
        b"page-0",
        b"page-1",
    ]
    assert pages[0].metadata == {
        "source_pdf": str(pdf_path),
        "page_number": 0,
        "dpi": 200,
    }


def test_pdf_adapter_repack_sorts_pages_and_saves_pdf(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "fitz", _fake_fitz_module())
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    first.write_bytes(b"first-image")
    second.write_bytes(b"second-image")
    output = tmp_path / "out.pdf"

    PDFAdapter().repack(
        iter([
            TranslatedPage(index=2, image_path=second),
            TranslatedPage(index=1, image_path=first),
        ]),
        output,
    )

    assert output.read_bytes() == b"first.png|second.png"
