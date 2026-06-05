"""Tests for mga.memory.retrieval — keyword search and context extraction."""

import json
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
        SceneState(
            scene_id="ch1_p1",
            chapter=1,
            page=1,
            mood="cheerful",
            characters=["sakura"],
            relationship_changes=["Sakura chooses to trust Ren"],
            key_dialogue=["I believe you."],
            future_impact="Sakura defends Ren in the next chapter",
        ),
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


def test_search_uses_memory_index_label(tmp_path):
    StateManager.upsert_character(
        tmp_path,
        CharacterState(character_id="akari", name_jp="Akari"),
    )
    index = StateManager.load(tmp_path)
    index.characters["akari"] = "Lamp Girl"
    StateManager.save(tmp_path, index)

    results = MemoryRetrieval.search(
        tmp_path,
        "Lamp Girl",
        entity_types=["characters"],
    )

    assert len(results) == 1
    assert results[0]["type"] == "character"
    assert results[0]["entity"].character_id == "akari"


def test_search_deduplicates_index_and_body_matches(tmp_path):
    StateManager.upsert_character(
        tmp_path,
        CharacterState(character_id="akari", name_jp="Akari"),
    )

    results = MemoryRetrieval.search(
        tmp_path,
        "Akari",
        entity_types=["characters"],
    )

    assert len(results) == 1
    assert results[0]["entity"].character_id == "akari"


def test_search_skips_stale_memory_index_entries(tmp_path):
    index = StateManager.load(tmp_path)
    index.characters["missing"] = "Lamp Girl"
    StateManager.save(tmp_path, index)

    results = MemoryRetrieval.search(
        tmp_path,
        "Lamp Girl",
        entity_types=["characters"],
    )

    assert results == []


def test_get_character_context(tmp_path):
    _setup(tmp_path)
    ctx = MemoryRetrieval.get_character_context(tmp_path, "sakura")
    assert ctx["name_jp"] == "桜"
    assert "speech_patterns" in ctx
    assert "catchphrases" in ctx
    assert ctx["relationship_speech"] == {}


def test_get_character_context_includes_relationship_speech(tmp_path):
    StateManager.upsert_character(
        tmp_path,
        CharacterState(
            character_id="akari",
            relationship_speech={
                "ren": {
                    "honorific_level": "polite",
                    "address": "Ren-sensei",
                    "sentence_style": "short polite sentences",
                },
            },
        ),
    )

    ctx = MemoryRetrieval.get_character_context(tmp_path, "akari")

    assert ctx["relationship_speech"] == {
        "ren": {
            "honorific_level": "polite",
            "address": "Ren-sensei",
            "sentence_style": "short polite sentences",
        },
    }


def test_get_character_context_reads_toml_profile_fallback(tmp_path):
    profile_dir = tmp_path / "character_profiles"
    profile_dir.mkdir()
    (profile_dir / "akari.toml").write_text(
        """
[meta]
character_id = "akari"
name_jp = "Akari"
name_zh = "Deng"
archetype = "protagonist"

[speech_patterns]
default = "quiet"

[catchphrases]
patterns = ["I understand"]

[tone_spectrum]
calm = "reserved"

[translation_notes]
addressing = "uses surnames"
""".strip(),
        encoding="utf-8",
    )

    ctx = MemoryRetrieval.get_character_context(tmp_path, "akari")

    assert ctx["character_id"] == "akari"
    assert ctx["name_jp"] == "Akari"
    assert ctx["name_zh"] == "Deng"
    assert ctx["archetype"] == "protagonist"
    assert ctx["speech_patterns"] == {"default": "quiet"}
    assert ctx["catchphrases"] == ["I understand"]
    assert ctx["tone_spectrum"] == {"calm": "reserved"}
    assert ctx["translation_notes"] == {"addressing": "uses surnames"}


def test_get_character_context_prefers_state_over_toml_profile(tmp_path):
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
    StateManager.upsert_character(
        tmp_path,
        CharacterState(character_id="akari", name_jp="Akari State", name_zh="Deng State"),
    )

    ctx = MemoryRetrieval.get_character_context(tmp_path, "akari")

    assert ctx["name_jp"] == "Akari State"
    assert ctx["name_zh"] == "Deng State"


def test_get_character_context_not_found(tmp_path):
    assert MemoryRetrieval.get_character_context(tmp_path, "nobody") == {}


def test_get_scene_context(tmp_path):
    _setup(tmp_path)
    ctx = MemoryRetrieval.get_scene_context(tmp_path, chapter=1, page=1)
    assert ctx["mood"] == "cheerful"
    assert ctx["relationship_changes"] == ["Sakura chooses to trust Ren"]
    assert ctx["key_dialogue"] == ["I believe you."]
    assert ctx["future_impact"] == "Sakura defends Ren in the next chapter"
    assert len(ctx["characters"]) == 1


def test_get_scene_context_not_found(tmp_path):
    assert MemoryRetrieval.get_scene_context(tmp_path, 99, 99) == {}


def test_get_recent_translations_reads_latest_history_per_speaker(tmp_path):
    translations_dir = tmp_path / "translations"
    translations_dir.mkdir()
    for index in range(6):
        page_id = f"p{index:03d}"
        (translations_dir / f"{page_id}.json").write_text(
            json.dumps({
                "page_id": page_id,
                "bubbles": [
                    {"bubble_id": f"b{index}", "speaker_id": "akari"},
                    {"bubble_id": f"r{index}", "speaker_id": "ren"},
                ],
                "translations": [
                    {"bubble_id": f"b{index}", "text": f"akari-{index}"},
                    {"bubble_id": f"r{index}", "text": f"ren-{index}"},
                ],
            }),
            encoding="utf-8",
        )

    recent = MemoryRetrieval.get_recent_translations(tmp_path, speakers=["akari"])

    assert recent == {"akari": ["akari-1", "akari-2", "akari-3", "akari-4", "akari-5"]}


def test_search_translation_memory_returns_ranked_source_matches(tmp_path):
    translations_dir = tmp_path / "translations"
    translations_dir.mkdir()
    (translations_dir / "p001.json").write_text(
        json.dumps(
            {
                "page_id": "p001",
                "bubbles": [
                    {
                        "bubble_id": "b1",
                        "source_text": "Where is the glass blade?",
                        "speaker_id": "akari",
                        "reading_order": 2,
                    },
                    {
                        "bubble_id": "b2",
                        "source_text": "The bridge is quiet.",
                        "speaker_id": "ren",
                        "reading_order": 1,
                    },
                ],
                "translations": [
                    {"bubble_id": "b1", "text": "玻璃刃在哪里？"},
                    {"bubble_id": "b2", "text": "桥上一片安静。"},
                ],
            }
        ),
        encoding="utf-8",
    )

    matches = MemoryRetrieval.search_translation_memory(
        tmp_path,
        "glass blade",
    )

    assert matches[0]["page_id"] == "p001"
    assert matches[0]["bubble_id"] == "b1"
    assert matches[0]["source_text"] == "Where is the glass blade?"
    assert matches[0]["translated_text"] == "玻璃刃在哪里？"
    assert matches[0]["speaker_id"] == "akari"
    assert matches[0]["score"] > 0
    assert len(matches) == 1

    context = MemoryRetrieval.format_translation_memory_context(matches)
    assert "## Translation Memory" in context
    assert "source: Where is the glass blade?" in context
    assert "translation: 玻璃刃在哪里？" in context
