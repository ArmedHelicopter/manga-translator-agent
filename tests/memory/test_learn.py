"""Tests for mga.memory.learn — LearnEngine pattern extraction."""

import json
from pathlib import Path

from mga.memory.learn import LearnEngine
from mga.memory.state import StateManager


def _write_normalized(output_dir: Path, pages: list[dict]):
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "external-baseline-text-normalized.json").write_text(
        json.dumps(pages, ensure_ascii=False), encoding="utf-8",
    )


def test_learn_empty(tmp_path):
    engine = LearnEngine(str(tmp_path))
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    summary = engine.learn_from_translations(str(output_dir))
    assert summary["pages_analysed"] == 0


def test_learn_extracts_characters(tmp_path):
    pages = [
        {
            "source_text_joined": "太郎が来る 太郎は良い",
            "translated_text_joined": "Taro comes Taro is good",
            "region_count": 3,
        },
        {
            "source_text_joined": "太郎と花子 太郎は元気",
            "translated_text_joined": "Taro and Hanako Taro is energetic",
            "region_count": 2,
        },
        {
            "source_text_joined": "太郎は勇敢だ 花子も",
            "translated_text_joined": "Taro is brave Hanako too",
            "region_count": 2,
        },
    ]
    output_dir = tmp_path / "output"
    _write_normalized(output_dir, pages)

    engine = LearnEngine(str(tmp_path))
    summary = engine.learn_from_translations(str(output_dir))
    assert summary["pages_analysed"] == 3
    assert summary["characters_learned"] >= 1

    chars = StateManager.list_characters(tmp_path)
    char_names = {c.name_jp for c in chars}
    assert "太郎" in char_names or "花子" in char_names


def test_learn_extracts_decisions(tmp_path):
    pages = [
        {"source_text_joined": "テスト", "translated_text_joined": "test", "region_count": 5},
    ]
    output_dir = tmp_path / "output"
    _write_normalized(output_dir, pages)

    engine = LearnEngine(str(tmp_path))
    summary = engine.learn_from_translations(str(output_dir))
    assert summary["decisions_learned"] >= 1

    decisions = StateManager.list_decisions(tmp_path)
    assert len(decisions) >= 1
