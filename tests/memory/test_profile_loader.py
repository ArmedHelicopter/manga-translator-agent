"""Tests for mga.memory.profile_loader — load, format, and convert character profiles."""

from pathlib import Path

from mga.memory.entities import CharacterState
from mga.memory.profile_loader import (
    format_profile_for_prompt,
    format_profiles_for_prompt,
    get_profile_as_dict,
    load_all_profiles,
    load_character_profile,
)
from mga.memory.state import StateManager


def _make_character(character_id: str, **kwargs) -> CharacterState:
    """Build a CharacterState with sensible defaults."""
    defaults = {
        "character_id": character_id,
        "name_jp": f"{character_id}_jp",
        "name_zh": f"{character_id}_zh",
    }
    defaults.update(kwargs)
    return CharacterState(**defaults)


def _save_character(project_dir: Path, character_id: str, **kwargs) -> CharacterState:
    """Create and persist a character via StateManager."""
    ch = _make_character(character_id, **kwargs)
    StateManager.upsert_character(project_dir, ch)
    return ch


# ── load_character_profile ─────────────────────────────────────


def test_load_character_profile_found(tmp_path):
    """Create a character via StateManager, load it back."""
    _save_character(tmp_path, "tanaka", name_jp="田中", name_zh="田中")

    result = load_character_profile(tmp_path, "tanaka")

    assert result is not None
    assert result.character_id == "tanaka"
    assert result.name_jp == "田中"
    assert result.name_zh == "田中"


def test_load_character_profile_not_found(tmp_path):
    """Returns None for a nonexistent character_id."""
    result = load_character_profile(tmp_path, "nonexistent")
    assert result is None


def test_load_character_profile_from_toml_fallback(tmp_path):
    profile_dir = tmp_path / "character_profiles" / "glass_and_blade"
    profile_dir.mkdir(parents=True)
    (profile_dir / "akari.toml").write_text(
        """
[meta]
character_id = "akari"
name_jp = "Akari"
name_zh = "Deng"
archetype = "protagonist"

[speech_patterns]
self_reference = ["boku", "watashi"]

[catchphrases]
patterns = ["I understand"]

[tone_spectrum]
default = "quiet"

[translation_notes]
addressing = "uses surnames"

[relationship_speech.ren]
honorific_level = "polite"
self_ref = "boku"
address = "Sensei"
sentence_style = "short polite sentences"
required_terms = ["Sensei"]
forbidden_terms = ["boss"]
""".strip(),
        encoding="utf-8",
    )

    result = load_character_profile(tmp_path, "akari")

    assert result is not None
    assert result.character_id == "akari"
    assert result.name_jp == "Akari"
    assert result.name_zh == "Deng"
    assert result.archetype == "protagonist"
    assert result.speech_patterns == {"self_reference": "boku, watashi"}
    assert result.catchphrases == ["I understand"]
    assert result.tone_spectrum == {"default": "quiet"}
    assert result.translation_notes == {"addressing": "uses surnames"}
    assert result.relationship_speech == {
        "ren": {
            "honorific_level": "polite",
            "self_ref": "boku",
            "address": "Sensei",
            "sentence_style": "short polite sentences",
            "required_terms": ["Sensei"],
            "forbidden_terms": ["boss"],
        }
    }


def test_load_character_profile_preserves_review_metadata(tmp_path):
    profile_dir = tmp_path / "character_profiles"
    profile_dir.mkdir()
    (profile_dir / "akari.toml").write_text(
        """
[meta]
character_id = "akari"
name_jp = "Akari"
last_reviewed_by = "human_editor_A"
last_reviewed_at = "2026-05-06T14:00:00Z"
last_reviewed_chapter = 1
confidence = 0.42
staleness_threshold = 10
""".strip(),
        encoding="utf-8",
    )

    result = load_character_profile(tmp_path, "akari")

    assert result is not None
    assert result.provenance["last_reviewed_by"] == "human_editor_A"
    assert result.provenance["last_reviewed_at"] == "2026-05-06T14:00:00Z"
    assert result.provenance["last_reviewed_chapter"] == 1
    assert result.provenance["confidence"] == 0.42
    assert result.provenance["staleness_threshold"] == 10


# ── load_all_profiles ──────────────────────────────────────────


def test_load_all_profiles(tmp_path):
    """Create 2 characters, verify dict with both."""
    _save_character(tmp_path, "alice", name_jp="アリス", name_zh="爱丽丝")
    _save_character(tmp_path, "bob", name_jp="ボブ", name_zh="鲍勃")

    profiles = load_all_profiles(tmp_path)

    assert isinstance(profiles, dict)
    assert len(profiles) == 2
    assert "alice" in profiles
    assert "bob" in profiles
    assert profiles["alice"].name_jp == "アリス"
    assert profiles["bob"].name_zh == "鲍勃"


def test_load_all_profiles_empty(tmp_path):
    """Empty directory returns empty dict."""
    profiles = load_all_profiles(tmp_path)
    assert profiles == {}


def test_load_all_profiles_merges_toml_and_state_with_state_precedence(tmp_path):
    profile_dir = tmp_path / "character_profiles"
    profile_dir.mkdir()
    (profile_dir / "akari.toml").write_text(
        """
[meta]
character_id = "akari"
name_jp = "Akari TOML"
name_zh = "Deng TOML"
""".strip(),
        encoding="utf-8",
    )
    (profile_dir / "ren.toml").write_text(
        """
[meta]
character_id = "ren"
name_jp = "Ren"
name_zh = "Ren"
""".strip(),
        encoding="utf-8",
    )
    _save_character(tmp_path, "akari", name_jp="Akari State", name_zh="Deng State")

    profiles = load_all_profiles(tmp_path)

    assert set(profiles) == {"akari", "ren"}
    assert profiles["akari"].name_jp == "Akari State"
    assert profiles["akari"].name_zh == "Deng State"
    assert profiles["ren"].name_jp == "Ren"


# ── format_profile_for_prompt ──────────────────────────────────


def test_format_profile_for_prompt(tmp_path):
    """Verify Chinese output contains all sections."""
    profile = _make_character(
        "hanako",
        name_jp="花子",
        name_zh="花子",
        archetype="tsundere",
        speech_patterns={"だ": "的", "よ": "哦"},
        catchphrases=["絶対に許さない", "ごめんなさい"],
        tone_spectrum={"casual": "随意", "formal": "正式"},
        translation_notes={"honorific": "保留です"},
    )

    result = format_profile_for_prompt(profile)

    assert "角色档案" in result
    assert "花子" in result
    assert "原型" in result
    assert "tsundere" in result
    assert "语言模式" in result
    assert "だ=的" in result
    assert "口头禅" in result
    assert "絶対に許さない" in result
    assert "语气" in result
    assert "随意" in result
    assert "翻译注意" in result
    assert "保留です" in result


def test_format_profile_minimal(tmp_path):
    """Profile with only name_jp and name_zh."""
    profile = _make_character("yuki", name_jp="雪", name_zh="雪")

    result = format_profile_for_prompt(profile)

    assert "角色档案" in result
    assert "雪" in result
    # Should NOT contain optional sections
    assert "原型" not in result
    assert "语言模式" not in result
    assert "口头禅" not in result


# ── format_profiles_for_prompt ─────────────────────────────────


def test_format_profiles_for_prompt_multiple(tmp_path):
    """Two profiles joined with double newline."""
    profiles = {
        "a": _make_character("a", name_jp="ア", name_zh="甲"),
        "b": _make_character("b", name_jp="イ", name_zh="乙"),
    }

    result = format_profiles_for_prompt(profiles)

    assert "角色档案" in result
    assert "甲" in result
    assert "乙" in result
    # Two profile sections separated by double newline
    assert "\n\n" in result


def test_format_profiles_for_prompt_empty(tmp_path):
    """Empty dict returns empty string."""
    result = format_profiles_for_prompt({})
    assert result == ""


# ── get_profile_as_dict ────────────────────────────────────────


def test_get_profile_as_dict(tmp_path):
    """Verify all 8 expected keys present."""
    profile = _make_character(
        "dict_test",
        name_jp="テスト",
        name_zh="测试",
        archetype="detective",
        speech_patterns={"だ": "的"},
        catchphrases=["やった"],
        tone_spectrum={"cool": "冷静"},
        translation_notes={"note": "value"},
    )

    result = get_profile_as_dict(profile)

    expected_keys = {
        "character_id",
        "name_jp",
        "name_zh",
        "archetype",
        "speech_patterns",
        "catchphrases",
        "tone_spectrum",
        "translation_notes",
        "relationship_speech",
    }
    assert set(result.keys()) == expected_keys
    assert result["character_id"] == "dict_test"
    assert result["name_jp"] == "テスト"
    assert result["name_zh"] == "测试"
    assert result["archetype"] == "detective"
    assert result["speech_patterns"] == {"だ": "的"}
    assert result["catchphrases"] == ["やった"]
    assert result["tone_spectrum"] == {"cool": "冷静"}
    assert result["translation_notes"] == {"note": "value"}


def test_get_profile_as_dict_includes_empty_relationship_speech():
    profile = CharacterState(character_id="akari")

    result = get_profile_as_dict(profile)

    assert result["relationship_speech"] == {}
