"""Tests for bilingual format adapter orchestration."""

from __future__ import annotations

from pathlib import Path

from mga.format import get_adapter
from mga.format.bilingual import BilingualAdapter
from mga.models import TranslatedPage


def test_extract_bilingual_reads_image_dir_with_metadata(tmp_path):
    (tmp_path / "page-02.png").write_bytes(b"two")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")
    (tmp_path / "page-01.jpg").write_bytes(b"one")

    pages = list(BilingualAdapter().extract(tmp_path))

    assert [page.index for page in pages] == [0, 1]
    assert [page.original_ref for page in pages] == ["page-01.jpg", "page-02.png"]
    assert [page.metadata for page in pages] == [
        {"filename": "page-01.jpg", "extension": ".jpg"},
        {"filename": "page-02.png", "extension": ".png"},
    ]


def test_repack_bilingual_resolves_originals_sorts_and_merges(tmp_path, monkeypatch):
    explicit_original = tmp_path / "original-explicit.png"
    fallback_originals = tmp_path / "originals"
    fallback_originals.mkdir()
    fallback_original = fallback_originals / "page_0002.jpg"
    translated_one = tmp_path / "translated-1.png"
    translated_two = tmp_path / "translated-2.png"
    missing_translated = tmp_path / "missing.png"
    explicit_original.write_bytes(b"original-1")
    fallback_original.write_bytes(b"original-2")
    translated_one.write_bytes(b"translated-1")
    translated_two.write_bytes(b"translated-2")

    create_calls = []

    def fake_create_bilingual_page(original, translated, output, page_number):
        create_calls.append((Path(original).name, Path(translated).name, page_number))
        Path(output).write_bytes(f"bilingual-{page_number}".encode("ascii"))

    merge_calls = []

    def fake_merge_bilingual_pages(image_paths, output_path):
        merge_calls.append(([Path(path).read_bytes() for path in image_paths], output_path))
        Path(output_path).write_bytes(b"pdf")

    monkeypatch.setattr("mga.format.bilingual.create_bilingual_page", fake_create_bilingual_page)
    monkeypatch.setattr("mga.format.bilingual.merge_bilingual_pages", fake_merge_bilingual_pages)

    output = tmp_path / "bilingual.pdf"
    pages = [
        TranslatedPage(index=2, image_path=translated_two),
        TranslatedPage(index=3, image_path=missing_translated),
        TranslatedPage(
            index=1,
            image_path=translated_one,
            page_json={"original_image_path": str(explicit_original)},
        ),
    ]

    BilingualAdapter().repack(iter(pages), output, originals_dir=fallback_originals)

    assert create_calls == [
        ("original-explicit.png", "translated-1.png", 2),
        ("page_0002.jpg", "translated-2.png", 3),
    ]
    assert merge_calls == [([b"bilingual-2", b"bilingual-3"], str(output))]
    assert output.read_bytes() == b"pdf"


def test_repack_bilingual_does_not_merge_without_valid_pairs(tmp_path, monkeypatch):
    merge_called = False

    def fake_merge_bilingual_pages(image_paths, output_path):
        nonlocal merge_called
        merge_called = True

    monkeypatch.setattr("mga.format.bilingual.merge_bilingual_pages", fake_merge_bilingual_pages)

    output = tmp_path / "bilingual.pdf"
    BilingualAdapter().repack(
        iter([TranslatedPage(index=1, image_path=tmp_path / "missing.png")]),
        output,
    )

    assert merge_called is False
    assert not output.exists()


def test_get_adapter_maps_bilingual_to_bilingual_adapter():
    assert isinstance(get_adapter("bilingual"), BilingualAdapter)
