"""Tests for mga.memory.state — StateManager CRUD operations."""

import json
from pathlib import Path

from mga.memory.entities import CharacterState, SceneState, TermState, DecisionState
from mga.memory.state import StateManager


def _proj(tmp_path: Path) -> Path:
    """Create a project directory with memory dirs."""
    (tmp_path / "memory" / "state").mkdir(parents=True)
    return tmp_path


def test_load_creates_dirs(tmp_path):
    idx = StateManager.load(tmp_path)
    assert idx.version == 1
    assert (tmp_path / "memory" / "state" / "characters").is_dir()


def test_upsert_and_get_character(tmp_path):
    proj = _proj(tmp_path)
    ch = CharacterState(character_id="tanaka", name_jp="田中", name_zh="田中", archetype="hero")
    StateManager.upsert_character(proj, ch)

    got = StateManager.get_character(proj, "tanaka")
    assert got is not None
    assert got.name_jp == "田中"
    assert got.archetype == "hero"


def test_list_characters(tmp_path):
    proj = _proj(tmp_path)
    StateManager.upsert_character(proj, CharacterState(character_id="a", name_jp="A"))
    StateManager.upsert_character(proj, CharacterState(character_id="b", name_jp="B"))
    chars = StateManager.list_characters(proj)
    assert len(chars) == 2


def test_upsert_and_get_scene(tmp_path):
    proj = _proj(tmp_path)
    sc = SceneState(scene_id="ch1_p1", chapter=1, page=1, mood="tense")
    StateManager.upsert_scene(proj, sc)

    got = StateManager.get_scene(proj, "ch1_p1")
    assert got is not None
    assert got.mood == "tense"


def test_upsert_and_get_term(tmp_path):
    proj = _proj(tmp_path)
    t = TermState(term_id="katana", term_jp="刀", term_zh="刀", frequency=5)
    StateManager.upsert_term(proj, t)

    got = StateManager.get_term(proj, "katana")
    assert got is not None
    assert got.term_jp == "刀"
    assert got.frequency == 5


def test_upsert_and_get_decision(tmp_path):
    proj = _proj(tmp_path)
    d = DecisionState(stage="translate", decision="use calque", confidence=0.8)
    StateManager.upsert_decision(proj, d)

    decisions = StateManager.list_decisions(proj)
    assert len(decisions) == 1
    assert decisions[0].decision == "use calque"


def test_get_nonexistent_returns_none(tmp_path):
    proj = _proj(tmp_path)
    assert StateManager.get_character(proj, "nobody") is None
    assert StateManager.get_scene(proj, "none") is None
    assert StateManager.get_term(proj, "none") is None
    assert StateManager.get_decision(proj, "none") is None


def test_index_updated_on_upsert(tmp_path):
    proj = _proj(tmp_path)
    StateManager.upsert_character(proj, CharacterState(character_id="c1", name_jp="C1"))
    idx = StateManager.load(proj)
    assert "c1" in idx.characters
    assert idx.characters["c1"] == "C1"
