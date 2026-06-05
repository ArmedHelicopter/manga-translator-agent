"""Tests for MOBI adapter dependency handling and Calibre delegation."""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import pytest

from mga.format.mobi_adapter import MOBIAdapter, _require_calibre
from mga.models import TranslatedPage


def test_require_calibre_raises_clear_error_when_unavailable(monkeypatch):
    monkeypatch.setattr("mga.format.mobi_adapter.shutil.which", lambda name: None)

    with pytest.raises(FileNotFoundError, match="MOBI support requires Calibre"):
        _require_calibre()


def test_extract_mobi_converts_to_epub_and_delegates(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "mga.format.mobi_adapter.shutil.which",
        lambda name: "ebook-convert" if name == "ebook-convert" else None,
    )

    mobi_path = tmp_path / "book.mobi"
    mobi_path.write_bytes(b"mobi")
    conversion_calls = []

    def fake_run(args, check, capture_output):
        assert check is True
        assert capture_output is True
        assert args[0] == "ebook-convert"
        assert Path(args[1]) == mobi_path
        epub_path = Path(args[2])
        conversion_calls.append(tuple(args))
        with zipfile.ZipFile(epub_path, "w") as zf:
            zf.writestr("OPS/page10.png", b"ten")
            zf.writestr("OPS/page2.png", b"two")
            zf.writestr("OPS/page1.jpg", b"one")
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr("mga.format.mobi_adapter.subprocess.run", fake_run)

    pages = list(MOBIAdapter().extract(mobi_path))

    assert len(conversion_calls) == 1
    assert [page.index for page in pages] == [0, 1, 2]
    assert [page.original_ref for page in pages] == [
        "OPS/page1.jpg",
        "OPS/page2.png",
        "OPS/page10.png",
    ]
    assert [page.metadata["epub_entry"] for page in pages] == [
        "OPS/page1.jpg",
        "OPS/page2.png",
        "OPS/page10.png",
    ]
    assert [Path(page.image_path).read_bytes() for page in pages] == [
        b"one",
        b"two",
        b"ten",
    ]


def test_repack_mobi_writes_cbz_compatible_zip_in_page_order(tmp_path):
    first = tmp_path / "translated-1.png"
    second = tmp_path / "translated-2.jpg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    output = tmp_path / "translated.mobi.zip"
    pages = [
        TranslatedPage(index=2, image_path=second),
        TranslatedPage(index=1, image_path=first),
    ]

    MOBIAdapter().repack(iter(pages), output)

    with zipfile.ZipFile(output) as zf:
        assert zf.namelist() == ["0001.png", "0002.jpg"]
        assert zf.read("0001.png") == b"first"
        assert zf.read("0002.jpg") == b"second"
