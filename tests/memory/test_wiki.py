"""Tests for mga.memory.wiki — WikiProjection Markdown generation."""

from pathlib import Path

from mga.memory.entities import (
    CharacterState,
    DecisionState,
    MemoryIndex,
    SceneState,
    TermState,
)
from mga.memory.wiki import WikiProjection


def test_character_page_generation():
    ch = CharacterState(
        character_id="tanaka",
        name_jp="田中",
        name_zh="田中",
        archetype="hero",
        speech_patterns={"ending_だ": "assertive"},
        catchphrases=["よろしく"],
    )
    md = WikiProjection.generate_character_page(ch)
    assert "# 田中" in md
    assert "speech_patterns" in md.lower() or "Speech Patterns" in md
    assert "よろしく" in md


def test_scene_page_generation():
    sc = SceneState(
        scene_id="ch1_p1", chapter=1, page=1,
        scene_description="Battle scene",
        mood="intense",
        characters=["tanaka"],
    )
    md = WikiProjection.generate_scene_page(sc)
    assert "ch1 p1" in md
    assert "Battle scene" in md
    assert "tanaka" in md


def test_term_page_generation():
    t = TermState(
        term_id="katana", term_jp="刀", term_zh="刀",
        frequency=5, cultural_weight="high", strategy="preserve",
    )
    md = WikiProjection.generate_term_page(t)
    assert "# 刀" in md
    assert "frequency: 5" in md.lower()


def test_decision_page_generation():
    d = DecisionState(
        decision_id="dec_1", stage="translate",
        decision="Use calque for honorifics", confidence=0.85,
        rationale="Preserves cultural flavor",
    )
    md = WikiProjection.generate_decision_page(d)
    assert "Use calque" in md
    assert "0.85" in md


def test_index_page_generation():
    idx = MemoryIndex(
        characters={"t": "田中"}, scenes={"s1": "scene1"},
    )
    md = WikiProjection.generate_index(idx)
    assert "田中" in md
    assert "scene1" in md


def test_write_all_creates_files(tmp_path):
    ch = CharacterState(character_id="c1", name_jp="C1")
    idx = MemoryIndex(characters={"c1": "C1"})
    # Need to save entity first so StateManager can find it
    from mga.memory.state import StateManager
    StateManager.upsert_character(tmp_path, ch)
    StateManager.save(tmp_path, idx)

    WikiProjection.write_all(tmp_path, idx)
    assert (tmp_path / "memory" / "characters" / "c1.md").exists()
    assert (tmp_path / "memory" / "indexes" / "index.md").exists()
