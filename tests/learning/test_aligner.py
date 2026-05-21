"""Tests for mga.learning.aligner — file pairing logic (Stage L1)."""

import pytest
from pathlib import Path

from mga.learning.aligner import align, align_from_flat_dirs
from mga.learning.models import PagePair


def _make_dirs(learn_dir: Path, orig_names: list[str], trans_names: list[str]):
    """Helper to create originals/ and translations/ with empty files."""
    orig = learn_dir / "originals"
    trans = learn_dir / "translations"
    orig.mkdir(parents=True)
    trans.mkdir(parents=True)
    for name in orig_names:
        (orig / name).write_text("")
    for name in trans_names:
        (trans / name).write_text("")


class TestAlignMangaPairs:
    def test_align_manga_pairs(self, tmp_path: Path):
        learn_dir = tmp_path / "learn"
        _make_dirs(learn_dir, ["page001.png", "page002.png"], ["page001.png", "page002.png"])

        pairs = align(tmp_path, learn_dir)

        assert len(pairs) == 2
        assert pairs[0].page_id == "page001"
        assert pairs[1].page_id == "page002"
        assert pairs[0].original_path.endswith("page001.png")
        assert pairs[0].translated_path.endswith("page001.png")

    def test_align_novel_pairs(self, tmp_path: Path):
        learn_dir = tmp_path / "learn"
        _make_dirs(learn_dir, ["ch01.txt", "ch02.txt"], ["ch01.txt", "ch02.txt"])

        pairs = align(tmp_path, learn_dir)

        assert len(pairs) == 2
        assert pairs[0].page_id == "ch01"
        assert pairs[1].page_id == "ch02"

    def test_align_mixed_extensions(self, tmp_path: Path):
        learn_dir = tmp_path / "learn"
        orig_names = ["page001.png", "chapter01.txt", "page002.jpg"]
        trans_names = ["page001.png", "chapter01.txt", "page002.jpg"]
        _make_dirs(learn_dir, orig_names, trans_names)

        pairs = align(tmp_path, learn_dir)

        assert len(pairs) == 3
        page_ids = {p.page_id for p in pairs}
        assert page_ids == {"page001", "chapter01", "page002"}

    def test_align_missing_translations(self, tmp_path: Path):
        learn_dir = tmp_path / "learn"
        _make_dirs(learn_dir, ["page001.png", "page002.png"], ["page001.png"])

        pairs = align(tmp_path, learn_dir)

        assert len(pairs) == 1
        assert pairs[0].page_id == "page001"

    def test_align_empty_dirs(self, tmp_path: Path):
        learn_dir = tmp_path / "learn"
        _make_dirs(learn_dir, [], [])

        pairs = align(tmp_path, learn_dir)

        assert pairs == []

    def test_align_missing_originals_dir(self, tmp_path: Path):
        learn_dir = tmp_path / "learn"
        (learn_dir / "translations").mkdir(parents=True)

        with pytest.raises(FileNotFoundError, match="Originals directory not found"):
            align(tmp_path, learn_dir)

    def test_align_missing_translations_dir(self, tmp_path: Path):
        learn_dir = tmp_path / "learn"
        (learn_dir / "originals").mkdir(parents=True)

        with pytest.raises(FileNotFoundError, match="Translations directory not found"):
            align(tmp_path, learn_dir)

    def test_align_from_flat_dirs(self, tmp_path: Path):
        orig_dir = tmp_path / "orig"
        trans_dir = tmp_path / "trans"
        orig_dir.mkdir()
        trans_dir.mkdir()
        (orig_dir / "page001.png").write_text("")
        (orig_dir / "page002.png").write_text("")
        (trans_dir / "page001.png").write_text("")
        (trans_dir / "page002.png").write_text("")

        pairs = align_from_flat_dirs(orig_dir, trans_dir)

        assert len(pairs) == 2
        assert pairs[0].page_id == "page001"
        assert pairs[1].page_id == "page002"

    def test_align_unknown_extensions(self, tmp_path: Path):
        learn_dir = tmp_path / "learn"
        _make_dirs(learn_dir, ["data.xyz", "page001.png"], ["data.xyz", "page001.png"])

        pairs = align(tmp_path, learn_dir)

        assert len(pairs) == 1
        assert pairs[0].page_id == "page001"

    def test_align_sorted_by_name(self, tmp_path: Path):
        learn_dir = tmp_path / "learn"
        _make_dirs(learn_dir, ["page003.png", "page001.png", "page002.png"],
                   ["page003.png", "page001.png", "page002.png"])

        pairs = align(tmp_path, learn_dir)

        assert [p.page_id for p in pairs] == ["page001", "page002", "page003"]

    def test_align_jpg_and_jpeg(self, tmp_path: Path):
        learn_dir = tmp_path / "learn"
        orig_names = ["a.jpg", "b.jpeg", "c.webp", "d.bmp"]
        _make_dirs(learn_dir, orig_names, orig_names)

        pairs = align(tmp_path, learn_dir)

        assert len(pairs) == 4

    def test_align_from_flat_dirs_unknown_ext(self, tmp_path: Path):
        orig_dir = tmp_path / "orig"
        trans_dir = tmp_path / "trans"
        orig_dir.mkdir()
        trans_dir.mkdir()
        (orig_dir / "file.xyz").write_text("")
        (trans_dir / "file.xyz").write_text("")

        pairs = align_from_flat_dirs(orig_dir, trans_dir)

        assert pairs == []
