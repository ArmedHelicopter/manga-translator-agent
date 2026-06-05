"""Tests for image directory format adapter behavior."""

from __future__ import annotations

from pathlib import Path

from mga.format import get_adapter
from mga.format.images import ImageDirAdapter
from mga.models import TranslatedPage


def test_extract_image_dir_reads_images_only_with_metadata(tmp_path):
    (tmp_path / "page-02.png").write_bytes(b"two")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    (tmp_path / "page-01.JPG").write_bytes(b"one")

    pages = list(ImageDirAdapter().extract(tmp_path))

    assert [page.index for page in pages] == [0, 1]
    assert [page.original_ref for page in pages] == ["page-01.JPG", "page-02.png"]
    assert [page.metadata for page in pages] == [
        {"filename": "page-01.JPG", "extension": ".jpg"},
        {"filename": "page-02.png", "extension": ".png"},
    ]
    assert [Path(page.image_path).read_bytes() for page in pages] == [b"one", b"two"]


def test_repack_image_dir_copies_existing_pages_to_zero_padded_names(tmp_path):
    first = tmp_path / "translated-1.png"
    second = tmp_path / "translated-2.jpg"
    missing = tmp_path / "missing.png"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    output = tmp_path / "out"
    pages = [
        TranslatedPage(index=2, image_path=second),
        TranslatedPage(index=1, image_path=first),
        TranslatedPage(index=3, image_path=missing),
    ]

    ImageDirAdapter().repack(iter(pages), output)

    assert (output / "0001.png").read_bytes() == b"first"
    assert (output / "0002.jpg").read_bytes() == b"second"
    assert not (output / "0003.png").exists()


def test_get_adapter_maps_images_to_image_dir_adapter():
    assert isinstance(get_adapter("images"), ImageDirAdapter)
