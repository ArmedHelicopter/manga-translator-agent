"""Tests for manga image EPUB adapter behavior."""

from __future__ import annotations

import zipfile
from pathlib import Path

from mga.format import get_adapter
from mga.format.epub_adapter import EPUBAdapter
from mga.models import TranslatedPage


def test_extract_epub_reads_images_in_natural_order(tmp_path):
    epub_path = tmp_path / "book.epub"
    with zipfile.ZipFile(epub_path, "w") as zf:
        zf.writestr("OPS/page10.png", b"ten")
        zf.writestr("OPS/chapter.xhtml", "<img src='page1.jpg'>")
        zf.writestr("OPS/page2.png", b"two")
        zf.writestr("OPS/page1.jpg", b"one")

    pages = list(EPUBAdapter().extract(epub_path))

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
    assert [page.metadata["epub_idx"] for page in pages] == [0, 1, 2]
    assert [Path(page.image_path).read_bytes() for page in pages] == [
        b"one",
        b"two",
        b"ten",
    ]


def test_repack_epub_preserves_entries_and_sorts_pages(tmp_path):
    first = tmp_path / "translated-1.png"
    second = tmp_path / "translated-2.jpg"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    output = tmp_path / "translated.epub"
    pages = [
        TranslatedPage(
            index=2,
            image_path=second,
            page_json={"epub_entry": "OPS/page2.jpg"},
        ),
        TranslatedPage(
            index=1,
            image_path=first,
            page_json={"epub_entry": "OPS/page1.png"},
        ),
    ]

    EPUBAdapter().repack(iter(pages), output)

    with zipfile.ZipFile(output) as zf:
        assert zf.namelist() == ["OPS/page1.png", "OPS/page2.jpg"]
        assert zf.read("OPS/page1.png") == b"first"
        assert zf.read("OPS/page2.jpg") == b"second"


def test_repack_epub_uses_default_image_name_without_original_entry(tmp_path):
    image = tmp_path / "translated.png"
    image.write_bytes(b"image")
    output = tmp_path / "translated.epub"

    EPUBAdapter().repack(iter([TranslatedPage(index=3, image_path=image)]), output)

    with zipfile.ZipFile(output) as zf:
        assert zf.namelist() == ["images/0003.png"]
        assert zf.read("images/0003.png") == b"image"


def test_get_adapter_maps_epub_to_epub_adapter():
    assert isinstance(get_adapter("epub"), EPUBAdapter)
