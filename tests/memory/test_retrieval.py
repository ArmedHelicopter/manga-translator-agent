"""Tests for mga.memory.retrieval — keyword search and context extraction."""

from pathlib import Path

from mga.memory.entities import CharacterState, SceneState
from mga.memory.retrieval import MemoryRetrieval
from mga.memory.state import StateManager


def _setup(tmp_path: Path):
    StateManager.upsert_character(
        tmp_path,
        CharacterState(
            character_id="sakura", name_jp="桜", name_zh="樱花",
            speech_patterns={"style": "casual"}, catchphrases=["がんばれ"],
        ),
    )
    StateManager.upsert_scene(
        tmp_path,
        SceneState(scene_id="ch1_p1", chapter=1, page=1, mood="cheerful", characters=["sakura"]),
    )


def test_search_finds_character(tmp_path):
    _setup(tmp_path)
    results = MemoryRetrieval.search(tmp_path, "桜")
    assert len(results) >= 1
    assert any(r["type"] == "character" for r in results)


def test_search_no_results(tmp_path):
    _setup(tmp_path)
    results = MemoryRetrieval.search(tmp_path, "zzzznonexistent")
    assert results == []


def test_search_entity_type_filter(tmp_path):
    _setup(tmp_path)
    results = MemoryRetrieval.search(tmp_path, "桜", entity_types=["scenes"])
    assert all(r["type"] == "scene" for r in results)


def test_get_character_context(tmp_path):
    _setup(tmp_path)
    ctx = MemoryRetrieval.get_character_context(tmp_path, "sakura")
    assert ctx["name_jp"] == "桜"
    assert "speech_patterns" in ctx
    assert "catchphrases" in ctx


def test_get_character_context_not_found(tmp_path):
    assert MemoryRetrieval.get_character_context(tmp_path, "nobody") == {}


def test_get_scene_context(tmp_path):
    _setup(tmp_path)
    ctx = MemoryRetrieval.get_scene_context(tmp_path, chapter=1, page=1)
    assert ctx["mood"] == "cheerful"
    assert len(ctx["characters"]) == 1


def test_get_scene_context_not_found(tmp_path):
    assert MemoryRetrieval.get_scene_context(tmp_path, 99, 99) == {}
