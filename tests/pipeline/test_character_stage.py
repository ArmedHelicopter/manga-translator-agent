"""Tests for CharacterAttributionStage memory context assembly."""

from __future__ import annotations

from mga.memory.entities import SceneState
from mga.memory.state import StateManager
from mga.models import Bubble, Page, ProjectConfig
from mga.pipeline.character_stage import CharacterAttributionStage
from mga.pipeline.stages import PipelineContext


def test_character_stage_uses_toml_profile_fallback_for_formal_speaker(tmp_path):
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

[tone_spectrum]
calm = "reserved"
""".strip(),
        encoding="utf-8",
    )

    context = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path)),
        pages=[
            Page(
                page_id="p001",
                bubbles=[
                    Bubble(
                        bubble_id="b001",
                        source_text="SOURCE",
                        speaker_id="akari",
                    ),
                ],
            ),
        ],
    )

    result = CharacterAttributionStage().execute(context)

    page_profile = result.memory_context["page_profiles"]["p001"]["akari"]
    assert page_profile["name_jp"] == "Akari"
    assert page_profile["name_zh"] == "Deng"
    assert page_profile["speech_patterns"] == {"default": "quiet"}
    assert result.memory_context["character_profiles"]["akari"] == page_profile


def test_character_stage_flags_stale_toml_profile_for_current_chapter(tmp_path):
    profile_dir = tmp_path / "character_profiles"
    profile_dir.mkdir()
    (profile_dir / "akari.toml").write_text(
        """
[meta]
character_id = "akari"
name_jp = "Akari"
last_reviewed_at = "2026-05-06T14:00:00Z"
last_reviewed_chapter = 1
confidence = 0.42
staleness_threshold = 10
""".strip(),
        encoding="utf-8",
    )

    context = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path)),
        pages=[
            Page(
                page_id="p001",
                bubbles=[
                    Bubble(
                        bubble_id="b001",
                        source_text="SOURCE",
                        speaker_id="akari",
                    ),
                ],
            ),
        ],
        metadata={"chapter_id": "ch12"},
    )

    result = CharacterAttributionStage().execute(context)

    assert result.memory_context["profile_warnings"] == [
        {
            "character_id": "akari",
            "category": "character.profile_stale",
            "current_chapter": 12,
            "last_reviewed_chapter": 1,
            "staleness_threshold": 10,
            "confidence": 0.42,
            "last_reviewed_at": "2026-05-06T14:00:00Z",
            "message": "Character profile for akari is stale by 11 chapters",
        }
    ]


def test_character_stage_does_not_flag_staleness_without_current_chapter(tmp_path):
    profile_dir = tmp_path / "character_profiles"
    profile_dir.mkdir()
    (profile_dir / "akari.toml").write_text(
        """
[meta]
character_id = "akari"
name_jp = "Akari"
last_reviewed_chapter = 1
staleness_threshold = 1
""".strip(),
        encoding="utf-8",
    )

    context = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path)),
        pages=[
            Page(
                page_id="p001",
                bubbles=[
                    Bubble(
                        bubble_id="b001",
                        source_text="SOURCE",
                        speaker_id="akari",
                    ),
                ],
            ),
        ],
    )

    result = CharacterAttributionStage().execute(context)

    assert result.memory_context["profile_warnings"] == []


def test_character_stage_loads_fictional_script_context(tmp_path):
    scripts_dir = tmp_path / "fictional_scripts"
    scripts_dir.mkdir()
    (scripts_dir / "abyss.toml").write_text(
        """
[meta]
name = "Abyss Script"
source = "Made in Abyss"
has_mapping = true

[mapping]
"*" = "a"
""".strip(),
        encoding="utf-8",
    )

    context = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path)),
        pages=[
            Page(
                page_id="p001",
                bubbles=[
                    Bubble(
                        bubble_id="b001",
                        source_text="SOURCE",
                    ),
                ],
            ),
        ],
    )

    result = CharacterAttributionStage().execute(context)

    assert result.memory_context["fictional_scripts"]["abyss"]["mapping"] == {"*": "a"}


def test_character_stage_loads_page_scene_context_for_current_chapter(tmp_path):
    StateManager.upsert_scene(
        tmp_path,
        SceneState(
            scene_id="ch3_p2_glass_room",
            chapter=3,
            page=2,
            scene_description="Akari confronts Ren in the glass room",
            mood="tense",
            narrative_summary="Ren hides what happened in the previous chapter",
            relationship_changes=["Akari stops trusting Ren"],
            key_dialogue=["Tell me the truth."],
            future_impact="Akari investigates alone next chapter",
            characters=["akari", "ren"],
        ),
    )

    context = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path)),
        pages=[
            Page(
                page_id="p002",
                page_index=1,
                bubbles=[
                    Bubble(
                        bubble_id="b001",
                        source_text="SOURCE",
                        speaker_id="akari",
                    ),
                ],
            ),
        ],
        metadata={"chapter_id": "ch3"},
    )

    result = CharacterAttributionStage().execute(context)

    scene_context = result.memory_context["scene_contexts"]["p002"]
    assert scene_context["scene_id"] == "ch3_p2_glass_room"
    assert scene_context["mood"] == "tense"
    assert scene_context["relationship_changes"] == ["Akari stops trusting Ren"]
    assert scene_context["key_dialogue"] == ["Tell me the truth."]
    assert scene_context["future_impact"] == "Akari investigates alone next chapter"
