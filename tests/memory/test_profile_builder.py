"""Tests for mga.memory.profile_builder — build and enrich character profiles."""

from pathlib import Path

from mga.memory.entities import CharacterState
from mga.memory.profile_builder import (
    build_and_save_profile,
    build_profile_from_translations,
    save_profile,
    update_catchphrases,
    update_speech_patterns,
)
from mga.memory.profile_loader import load_character_profile
from mga.memory.state import StateManager


# ── build_profile_from_translations ────────────────────────────


def test_build_new_profile(tmp_path):
    """Creates a new CharacterState when none exists."""
    profile = build_profile_from_translations(
        tmp_path, "newchar", name_jp="新キャラ", name_zh="新角色",
    )

    assert isinstance(profile, CharacterState)
    assert profile.character_id == "newchar"
    assert profile.name_jp == "新キャラ"
    assert profile.name_zh == "新角色"


def test_build_existing_profile(tmp_path):
    """Loads an existing profile instead of creating a new one."""
    # Pre-save a profile with specific data
    original = CharacterState(
        character_id="existing",
        name_jp="既存",
        name_zh="已有",
        archetype="villain",
    )
    StateManager.upsert_character(tmp_path, original)

    profile = build_profile_from_translations(
        tmp_path, "existing", name_jp="ignored", name_zh="ignored",
    )

    # Should load the existing one, not create a new one
    assert profile.character_id == "existing"
    assert profile.name_jp == "既存"
    assert profile.name_zh == "已有"
    assert profile.archetype == "villain"


# ── update_speech_patterns ─────────────────────────────────────


def test_update_speech_patterns(tmp_path):
    """Verify Japanese ending particle is extracted."""
    profile = CharacterState(character_id="speech_test")

    result = update_speech_patterns(profile, "元気だよ。", "很有精神哦。")

    # The regex captures the full ending before punctuation: "だよ"
    assert "だよ" in result.speech_patterns
    assert len(result.speech_patterns) == 1


def test_update_speech_patterns_no_match(tmp_path):
    """Text without particles doesn't break."""
    profile = CharacterState(character_id="no_match")

    result = update_speech_patterns(profile, "Hello", "你好")

    # No particles found, speech_patterns should remain empty
    assert len(result.speech_patterns) == 0


# ── update_catchphrases ────────────────────────────────────────


def test_update_catchphrases(tmp_path):
    """Repeated CJK phrases are added to catchphrases."""
    profile = CharacterState(character_id="catchphrase_test")

    # Source text with a distinctive phrase
    result = update_catchphrases(profile, "私は正義の味方だ。正義の味方として戦う。")

    # Should detect phrases from the text
    assert len(result.catchphrases) > 0


# ── save and reload ────────────────────────────────────────────


def test_save_and_reload(tmp_path):
    """Save a profile, then load it back via StateManager."""
    profile = CharacterState(
        character_id="save_test",
        name_jp="保存テスト",
        name_zh="保存测试",
        archetype="hero",
    )

    save_profile(tmp_path, profile)
    loaded = load_character_profile(tmp_path, "save_test")

    assert loaded is not None
    assert loaded.character_id == "save_test"
    assert loaded.name_jp == "保存テスト"
    assert loaded.archetype == "hero"


# ── build_and_save_profile (e2e) ──────────────────────────────


def test_build_and_save_profile_e2e(tmp_path):
    """Full flow: build, enrich with source text, and save."""
    result = build_and_save_profile(
        tmp_path,
        character_id="e2e_char",
        name_jp="テスト太郎",
        name_zh="测试太郎",
        source_text="おはようございます！元気ですか？",
        translated_text="早上好！你好吗？",
    )

    assert isinstance(result, CharacterState)
    assert result.character_id == "e2e_char"
    assert result.name_jp == "テスト太郎"

    # Verify it was persisted
    loaded = load_character_profile(tmp_path, "e2e_char")
    assert loaded is not None
    assert loaded.name_jp == "テスト太郎"

    # Speech patterns should have been extracted
    assert len(loaded.speech_patterns) > 0
    assert (tmp_path / "character_profiles" / "e2e_char.toml").exists()


def test_save_profile_writes_toml_asset(tmp_path):
    profile = CharacterState(
        character_id="akari",
        name_jp="Akari",
        name_zh="Deng",
        archetype="protagonist",
        speech_patterns={"default": "polite"},
        catchphrases=["I understand"],
        tone_spectrum={"default": "quiet"},
        translation_notes={"addressing": "uses surnames"},
    )

    save_profile(tmp_path, profile)

    profile_toml = (tmp_path / "character_profiles" / "akari.toml").read_text(
        encoding="utf-8"
    )
    assert 'character_id = "akari"' in profile_toml
    assert 'name_jp = "Akari"' in profile_toml
    assert 'archetype = "protagonist"' in profile_toml
    assert 'default = "polite"' in profile_toml
    assert '"I understand"' in profile_toml


def test_save_profile_writes_relationship_speech_toml_asset(tmp_path):
    relationship_speech = {
        "ren": {
            "honorific_level": "polite",
            "self_ref": "boku",
            "required_terms": ["Sensei"],
            "forbidden_terms": ["boss"],
        }
    }
    profile = CharacterState(
        character_id="akari",
        name_jp="Akari",
        name_zh="Deng",
        relationship_speech=relationship_speech,
    )

    save_profile(tmp_path, profile)

    profile_toml = (tmp_path / "character_profiles" / "akari.toml").read_text(
        encoding="utf-8"
    )
    assert "[relationship_speech.ren]" in profile_toml
    assert 'honorific_level = "polite"' in profile_toml
    assert "required_terms" in profile_toml
    assert '"Sensei"' in profile_toml

    fallback_project = tmp_path / "fallback"
    fallback_profiles = fallback_project / "character_profiles"
    fallback_profiles.mkdir(parents=True)
    (fallback_profiles / "akari.toml").write_text(profile_toml, encoding="utf-8")

    loaded = load_character_profile(fallback_project, "akari")

    assert loaded is not None
    assert loaded.relationship_speech == relationship_speech


def test_save_profile_drops_nested_none_values_for_toml(tmp_path):
    """TOML has no null; nested None from provider notes must not crash save."""
    profile = CharacterState(
        character_id="nullable_notes",
        voice_evolutions=[
            {"chapter": "ch1", "observations": [{"term": "ボー", "explanation": None}, None]},
        ],
    )

    save_profile(tmp_path, profile)

    profile_toml = (tmp_path / "character_profiles" / "nullable_notes.toml").read_text(
        encoding="utf-8"
    )
    assert "nullable_notes" in profile_toml
    assert "voice_evolution" in profile_toml
    assert "observations" in profile_toml
    assert "explanation" not in profile_toml
