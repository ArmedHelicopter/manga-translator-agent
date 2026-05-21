"""Tests for mga.memory.seeding — seed memory from external runtime output."""

import json
from pathlib import Path

from mga.memory.seeding import seed_memory_from_external_output
from mga.memory.state import StateManager


def _write_normalized(output_dir: Path, pages: list[dict]):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "external-baseline-text-normalized.json").write_text(
        json.dumps(pages, ensure_ascii=False), encoding="utf-8",
    )


def test_seed_empty_output(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    summary = seed_memory_from_external_output(str(tmp_path), str(output_dir))
    assert summary["pages_processed"] == 0
    assert summary["characters_seeded"] == 0


def test_seed_characters_and_terms(tmp_path):
    # Need names appearing on 3+ pages with total freq >= 5
    pages = [
        {
            "page_id": "page-0001",
            "source_text_joined": "田中太郎さんは良い人だ 田中太郎さんは優しい",
            "translated_text_joined": "Tanaka Taro is a good person Tanaka Taro is kind",
            "region_count": 3,
        },
        {
            "page_id": "page-0002",
            "source_text_joined": "田中太郎さんと一緒に 田中太郎さんが来た",
            "translated_text_joined": "Together with Tanaka Taro Tanaka Taro came",
            "region_count": 2,
        },
        {
            "page_id": "page-0003",
            "source_text_joined": "田中太郎さんが待っている 田中太郎さんだ",
            "translated_text_joined": "Tanaka Taro is waiting It is Tanaka Taro",
            "region_count": 2,
        },
    ]
    output_dir = tmp_path / "output"
    _write_normalized(output_dir, pages)

    summary = seed_memory_from_external_output(str(tmp_path), str(output_dir))
    assert summary["pages_processed"] == 3
    assert summary["scenes_seeded"] == 3

    chars = StateManager.list_characters(tmp_path)
    assert len(chars) >= 1  # 田中太郎 should be detected


def test_seed_scenes(tmp_path):
    pages = [
        {"page_id": "p001", "source_text_joined": "テスト", "region_count": 1},
        {"page_id": "p002", "source_text_joined": "テスト2", "region_count": 2},
    ]
    output_dir = tmp_path / "output"
    _write_normalized(output_dir, pages)

    summary = seed_memory_from_external_output(str(tmp_path), str(output_dir))
    assert summary["scenes_seeded"] == 2
    scenes = StateManager.list_scenes(tmp_path)
    assert len(scenes) == 2
