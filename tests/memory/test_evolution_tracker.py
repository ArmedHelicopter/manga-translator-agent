"""Tests for mga.memory.evolution_tracker — EvolutionTracker."""

from pathlib import Path

from mga.memory.entities import CharacterState
from mga.memory.evolution_tracker import EvolutionTracker
from mga.memory.state import StateManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup_character(project_dir: Path, character_id: str = "tanaka") -> None:
    """Seed a character profile with known speech patterns and tone."""
    StateManager.upsert_character(project_dir, CharacterState(
        character_id=character_id,
        name_jp="田中",
        name_zh="田中",
        archetype="hero",
        speech_patterns={
            "だ": "男性随意",
            "ですよ": "礼貌",
        },
        tone_spectrum={
            "battle": "激昂",
            "casual": "轻松",
        },
    ))


# ---------------------------------------------------------------------------
# detect_changes
# ---------------------------------------------------------------------------

def test_detect_changes_new_pattern(tmp_path: Path):
    _setup_character(tmp_path)
    tracker = EvolutionTracker(tmp_path)

    changes = tracker.detect_changes(
        "tanaka",
        new_speech_patterns={"わ": "女性语"},
        chapter=2, page=5,
    )
    assert len(changes) == 1
    assert changes[0]["type"] == "speech_pattern_new"
    assert changes[0]["new_value"] == "女性语"
    assert changes[0]["chapter"] == 2


def test_detect_changes_changed_pattern(tmp_path: Path):
    _setup_character(tmp_path)
    tracker = EvolutionTracker(tmp_path)

    changes = tracker.detect_changes(
        "tanaka",
        new_speech_patterns={"だ": "成熟男性"},
        chapter=3, page=1,
    )
    assert len(changes) == 1
    assert changes[0]["type"] == "speech_pattern_changed"
    assert changes[0]["old_value"] == "男性随意"
    assert changes[0]["new_value"] == "成熟男性"


def test_detect_changes_no_changes(tmp_path: Path):
    _setup_character(tmp_path)
    tracker = EvolutionTracker(tmp_path)

    changes = tracker.detect_changes(
        "tanaka",
        new_speech_patterns={"だ": "男性随意", "ですよ": "礼貌"},
    )
    assert changes == []


def test_detect_changes_tone_new(tmp_path: Path):
    _setup_character(tmp_path)
    tracker = EvolutionTracker(tmp_path)

    changes = tracker.detect_changes(
        "tanaka",
        new_speech_patterns={},
        new_tone={"romantic": "温柔"},
        chapter=5,
    )
    assert len(changes) == 1
    assert changes[0]["type"] == "tone_new"
    assert changes[0]["new_value"] == "温柔"


def test_detect_changes_tone_changed(tmp_path: Path):
    _setup_character(tmp_path)
    tracker = EvolutionTracker(tmp_path)

    changes = tracker.detect_changes(
        "tanaka",
        new_speech_patterns={},
        new_tone={"battle": "冷静"},
        chapter=4,
    )
    assert len(changes) == 1
    assert changes[0]["type"] == "tone_changed"
    assert changes[0]["old_value"] == "激昂"
    assert changes[0]["new_value"] == "冷静"


def test_detect_changes_unknown_character(tmp_path: Path):
    tracker = EvolutionTracker(tmp_path)
    changes = tracker.detect_changes("ghost", {"あ": "test"})
    assert changes == []


# ---------------------------------------------------------------------------
# record_changes
# ---------------------------------------------------------------------------

def test_record_changes(tmp_path: Path):
    _setup_character(tmp_path)
    tracker = EvolutionTracker(tmp_path)

    # Use string "None" instead of None for old_value since TOML has no null type
    changes = [
        {"type": "speech_pattern_new", "character_id": "tanaka",
         "field": "speech_patterns.わ", "old_value": "", "new_value": "女性语",
         "chapter": 2, "page": 5, "timestamp": "2026-01-01T00:00:00"},
    ]
    tracker.record_changes(changes)

    changelog = tracker.get_changelog()
    assert len(changelog) == 1
    assert changelog[0]["character_id"] == "tanaka"


def test_record_changes_appends(tmp_path: Path):
    _setup_character(tmp_path)
    tracker = EvolutionTracker(tmp_path)

    c1 = [{"type": "speech_pattern_new", "character_id": "tanaka",
            "field": "speech_patterns.わ", "new_value": "女性语",
            "chapter": 1, "page": 0, "timestamp": "2026-01-01T00:00:00"}]
    c2 = [{"type": "tone_new", "character_id": "tanaka",
            "field": "tone_spectrum.romantic", "new_value": "温柔",
            "chapter": 2, "page": 0, "timestamp": "2026-01-02T00:00:00"}]

    tracker.record_changes(c1)
    tracker.record_changes(c2)

    changelog = tracker.get_changelog()
    assert len(changelog) == 2


def test_record_changes_empty_list(tmp_path: Path):
    tracker = EvolutionTracker(tmp_path)
    tracker.record_changes([])  # should be a no-op
    assert not tracker._changelog_path.exists()


# ---------------------------------------------------------------------------
# update_profile
# ---------------------------------------------------------------------------

def test_update_profile(tmp_path: Path):
    _setup_character(tmp_path)
    tracker = EvolutionTracker(tmp_path)

    changes = [
        {"type": "speech_pattern_new", "character_id": "tanaka",
         "field": "speech_patterns.わ", "old_value": None, "new_value": "女性语",
         "chapter": 2, "page": 5, "timestamp": "2026-01-01T00:00:00"},
        {"type": "tone_changed", "character_id": "tanaka",
         "field": "tone_spectrum.battle", "old_value": "激昂", "new_value": "冷静",
         "chapter": 2, "page": 5, "timestamp": "2026-01-01T00:00:00"},
    ]

    profile = tracker.update_profile("tanaka", changes)
    assert profile is not None
    assert profile.speech_patterns["わ"] == "女性语"
    assert profile.tone_spectrum["battle"] == "冷静"
    # voice_evolutions should have been appended
    assert len(profile.voice_evolutions) == 1
    assert profile.voice_evolutions[0]["chapter"] == 2


def test_update_profile_unknown_character(tmp_path: Path):
    tracker = EvolutionTracker(tmp_path)
    result = tracker.update_profile("ghost", [])
    assert result is None


# ---------------------------------------------------------------------------
# get_changelog / get_changes_for_character
# ---------------------------------------------------------------------------

def test_get_changelog(tmp_path: Path):
    _setup_character(tmp_path)
    tracker = EvolutionTracker(tmp_path)

    # No file yet
    assert tracker.get_changelog() == []

    changes = [{"type": "speech_pattern_new", "character_id": "tanaka",
                "field": "speech_patterns.わ", "new_value": "女性语",
                "chapter": 2, "page": 0, "timestamp": "2026-01-01T00:00:00"}]
    tracker.record_changes(changes)
    assert len(tracker.get_changelog()) == 1


def test_get_changes_for_character(tmp_path: Path):
    _setup_character(tmp_path)
    StateManager.upsert_character(tmp_path, CharacterState(
        character_id="sato", name_jp="佐藤", name_zh="佐藤",
        speech_patterns={"だ": "男性"},
    ))
    tracker = EvolutionTracker(tmp_path)

    tracker.record_changes([
        {"type": "speech_pattern_new", "character_id": "tanaka",
         "field": "speech_patterns.わ", "new_value": "女性语",
         "chapter": 1, "page": 0, "timestamp": "2026-01-01T00:00:00"},
        {"type": "speech_pattern_new", "character_id": "sato",
         "field": "speech_patterns.ね", "new_value": "撒娇",
         "chapter": 2, "page": 0, "timestamp": "2026-01-02T00:00:00"},
    ])

    tanaka_changes = tracker.get_changes_for_character("tanaka")
    assert len(tanaka_changes) == 1
    assert tanaka_changes[0]["character_id"] == "tanaka"

    sato_changes = tracker.get_changes_for_character("sato")
    assert len(sato_changes) == 1
    assert sato_changes[0]["character_id"] == "sato"
