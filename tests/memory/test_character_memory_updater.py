"""Tests for page-sequential character memory updates."""

from mga.memory.character_memory_updater import (
    CharacterMemoryUpdater,
    infer_speech_style,
    style_translation_rule,
)
from mga.memory.entities import CharacterState
from mga.memory.state import StateManager
from mga.models import Bubble, Page


def test_update_from_translation_creates_character_and_trace(tmp_path):
    updater = CharacterMemoryUpdater(tmp_path)
    bubble = Bubble(
        bubble_id="b1",
        speaker_id="akari",
        source_text="おはようございます。",
    )

    result = updater.update_from_translation(
        speaker="akari",
        bubble=bubble,
        page_id="p001",
        translated_text="好的。",
        memory_before={},
        prompt="Source: おはようございます。",
    )

    profile = StateManager.get_character(tmp_path, "akari")
    assert profile is not None
    assert profile.tone_spectrum["observed_style"] == "礼貌、克制、句尾偏正式"
    assert profile.translation_notes["style_rule"] == (
        "中文译文使用礼貌克制表达，可使用“请”“您”等语气。"
    )
    assert profile.speech_patterns["latest_source_sample"] == "おはようございます。"
    assert profile.provenance["evidence_lines"] == ["おはようございます。"]

    assert result.memory_after["character_id"] == "akari"
    assert result.trace_item["memory_before"] == {}
    assert result.trace_item["memory_after"] == result.memory_after
    assert result.trace_item["prompt_excerpt"] == "Source: おはようございます。"


def test_update_from_translation_appends_observations_without_duplicate_evidence(tmp_path):
    updater = CharacterMemoryUpdater(tmp_path)
    StateManager.upsert_character(
        tmp_path,
        CharacterState(
            character_id="ren",
            name_jp="ren",
            provenance={
                "evidence_lines": ["そんなの知るかよ。"],
                "translation_observations": [],
            },
        ),
    )
    bubble = Bubble(
        bubble_id="b2",
        speaker_id="ren",
        source_text="そんなの知るかよ。",
    )

    updater.update_from_translation(
        speaker="ren",
        bubble=bubble,
        page_id="p002",
        translated_text="少废话。",
        memory_before={},
        prompt="prompt",
    )

    profile = StateManager.get_character(tmp_path, "ren")
    assert profile is not None
    assert profile.provenance["evidence_lines"] == ["そんなの知るかよ。"]
    assert profile.provenance["translation_observations"][-1] == {
        "page_id": "p002",
        "bubble_id": "b2",
        "source_text": "そんなの知るかよ。",
        "translated_text": "少废话。",
    }
    assert profile.provenance["last_updated_page"] == "p002"


def test_profiles_for_page_returns_only_persisted_formal_speakers(tmp_path):
    updater = CharacterMemoryUpdater(tmp_path)
    StateManager.upsert_character(
        tmp_path,
        CharacterState(
            character_id="akari",
            name_jp="akari",
            tone_spectrum={"observed_style": "礼貌"},
        ),
    )
    page = Page(
        page_id="p002",
        bubbles=[
            Bubble(bubble_id="b1", source_text="x", speaker_id="akari"),
            Bubble(bubble_id="b2", source_text="y", speaker_id="missing"),
            Bubble(bubble_id="b3", source_text="z", provisional_speaker="vision-only"),
            Bubble(bubble_id="b4", source_text="w", speaker_name="akari"),
        ],
    )

    profiles = updater.profiles_for_page(page)

    assert set(profiles) == {"akari"}
    assert profiles["akari"]["tone_spectrum"]["observed_style"] == "礼貌"


def test_infer_speech_style_rules_are_stable():
    assert infer_speech_style("ありがとうございます。") == (
        "polite",
        "礼貌、克制、句尾偏正式",
    )
    assert infer_speech_style("早くしろ。") == (
        "rough",
        "粗鲁、直接、句尾偏口语",
    )
    assert infer_speech_style("はい。") == ("neutral", "中性、平稳")
    assert style_translation_rule("neutral") == "中文译文保持自然中性。"
