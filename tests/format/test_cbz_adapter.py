"""Tests for ZIP-backed CBZ format adapter behavior."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from mga.format import get_adapter
from mga.format.cbz_adapter import CBZAdapter
from mga.models import TranslatedPage


def test_extract_cbz_reads_images_in_natural_order(tmp_path):
    cbz_path = tmp_path / "chapter.cbz"
    with zipfile.ZipFile(cbz_path, "w") as zf:
        zf.writestr("pages/page10.png", b"ten")
        zf.writestr("notes.txt", b"ignore me")
        zf.writestr("pages/page2.png", b"two")
        zf.writestr("pages/page1.jpg", b"one")

    pages = list(CBZAdapter().extract(cbz_path))

    assert [page.index for page in pages] == [0, 1, 2]
    assert [page.original_ref for page in pages] == [
        "pages/page1.jpg",
        "pages/page2.png",
        "pages/page10.png",
    ]
    assert [page.metadata["archive_entry"] for page in pages] == [
        "pages/page1.jpg",
        "pages/page2.png",
        "pages/page10.png",
    ]
    assert [Path(page.image_path).read_bytes() for page in pages] == [
        b"one",
        b"two",
        b"ten",
    ]


def test_repack_cbz_preserves_archive_entries(tmp_path):
    first = tmp_path / "translated-1.png"
    second = tmp_path / "translated-2.jpg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    output = tmp_path / "translated.cbz"
    pages = [
        TranslatedPage(
            index=2,
            image_path=second,
            page_json={"archive_entry": "pages/page2.jpg"},
        ),
        TranslatedPage(
            index=1,
            image_path=first,
            page_json={"archive_entry": "pages/page1.png"},
        ),
    ]

    CBZAdapter().repack(iter(pages), output)

    with zipfile.ZipFile(output) as zf:
        assert zf.namelist() == ["pages/page1.png", "pages/page2.jpg"]
        assert zf.read("pages/page1.png") == b"first"
        assert zf.read("pages/page2.jpg") == b"second"


def test_extract_cbr_raises_clear_error_when_unrar_is_unavailable(tmp_path, monkeypatch):
    cbr_path = tmp_path / "chapter.cbr"
    cbr_path.write_bytes(b"rar")

    def fake_run(*args, **kwargs):
        raise FileNotFoundError()

    monkeypatch.setattr("mga.format.cbz_adapter.subprocess.run", fake_run)

    with pytest.raises(FileNotFoundError, match="support CBR files"):
        list(CBZAdapter().extract(cbr_path))


def test_extract_cbr_invokes_unrar_and_reads_images_in_natural_order(tmp_path, monkeypatch):
    cbr_path = tmp_path / "chapter.cbr"
    cbr_path.write_bytes(b"rar")
    calls = []

    def fake_run(args, check, capture_output):
        assert check is True
        assert capture_output is True
        assert args[:4] == ["unrar", "x", "-o+", "-inul"]
        assert Path(args[4]) == cbr_path
        extract_dir = Path(args[5])
        calls.append(tuple(args))
        (extract_dir / "pages").mkdir(parents=True)
        (extract_dir / "pages" / "page10.png").write_bytes(b"ten")
        (extract_dir / "pages" / "page2.png").write_bytes(b"two")
        (extract_dir / "pages" / "page1.jpg").write_bytes(b"one")
        (extract_dir / "pages" / "notes.txt").write_text("ignore", encoding="utf-8")

    monkeypatch.setattr("mga.format.cbz_adapter.subprocess.run", fake_run)

    pages = list(CBZAdapter().extract(cbr_path))

    expected_entries = [
        str(Path("pages") / "page1.jpg"),
        str(Path("pages") / "page2.png"),
        str(Path("pages") / "page10.png"),
    ]
    assert len(calls) == 1
    assert [page.index for page in pages] == [0, 1, 2]
    assert [page.original_ref for page in pages] == expected_entries
    assert [page.metadata["archive_entry"] for page in pages] == expected_entries
    assert [Path(page.image_path).read_bytes() for page in pages] == [
        b"one",
        b"two",
        b"ten",
    ]


def test_get_adapter_maps_cbr_to_shared_cbz_adapter():
    assert isinstance(get_adapter("cbr"), CBZAdapter)
