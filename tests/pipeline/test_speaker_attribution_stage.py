"""Tests for conservative speaker attribution before translation memory."""

from __future__ import annotations

import json

from mga.memory.entities import CharacterState
from mga.memory.state import StateManager
from mga.models import Bubble, Page, ProjectConfig
from mga.pipeline.speaker_attribution_stage import SpeakerAttributionStage
from mga.pipeline.stages import PipelineContext
from mga.pipeline.translation_stage import TranslationStage


class FakeTranslationProvider:
    def chat(self, messages):
        return json.dumps({"text": "好的。", "footnotes": [], "rationale": ""}, ensure_ascii=False)


def test_speaker_attribution_promotes_exact_known_profile_match(tmp_path):
    StateManager.upsert_character(
        tmp_path,
        CharacterState(character_id="akari", name_jp="灯里", name_zh="灯里"),
    )
    page = Page(
        page_id="p001",
        bubbles=[
            Bubble(
                bubble_id="b1",
                source_text="おはよう。",
                provisional_speaker="灯里",
            ),
            Bubble(
                bubble_id="b2",
                source_text="またね。",
                provisional_speaker="灯里",
            ),
        ],
    )
    ctx = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path)),
        pages=[page],
    )

    result = SpeakerAttributionStage().execute(ctx)

    assert result.pages[0].bubbles[0].speaker_id == "akari"
    assert result.pages[0].bubbles[1].speaker_id == "akari"
    trace = result.artifacts["speaker_attribution"]["trace"]
    assert trace[0]["accepted"] is True
    assert trace[0]["reason"] == "speaker hint exactly matches existing character profile"
    assert trace[1]["accepted"] is True
    assert trace[1]["reason"] == "same-page speaker hint already matched a known character"


def test_speaker_attribution_keeps_generic_provisional_speaker_unassigned(tmp_path):
    StateManager.upsert_character(
        tmp_path,
        CharacterState(character_id="akari", name_jp="灯里", name_zh="灯里"),
    )
    page = Page(
        page_id="p001",
        bubbles=[
            Bubble(
                bubble_id="b1",
                source_text="大丈夫？",
                provisional_speaker="girl-near-door",
            ),
        ],
    )
    ctx = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path)),
        pages=[page],
    )

    result = SpeakerAttributionStage().execute(ctx)

    assert result.pages[0].bubbles[0].speaker_id is None
    trace = result.artifacts["speaker_attribution"]["trace"]
    assert trace == [
        {
            "provisional_speaker": "girl-near-door",
            "speaker_name": None,
            "assigned_speaker_id": None,
            "confidence": 0.1,
            "accepted": False,
            "reason": "generic provisional speaker is not formal attribution",
            "page_id": "p001",
            "bubble_id": "b1",
        }
    ]


def test_speaker_attribution_preserves_existing_speaker_id(tmp_path):
    page = Page(
        page_id="p001",
        bubbles=[
            Bubble(
                bubble_id="b1",
                source_text="おはよう。",
                speaker_id="manual",
                provisional_speaker="girl-near-door",
            ),
        ],
    )
    ctx = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path)),
        pages=[page],
    )

    result = SpeakerAttributionStage().execute(ctx)

    assert result.pages[0].bubbles[0].speaker_id == "manual"
    trace = result.artifacts["speaker_attribution"]["trace"]
    assert trace[0]["accepted"] is True
    assert trace[0]["confidence"] == 1.0


def test_translation_stage_does_not_persist_bare_speaker_name(tmp_path, monkeypatch):
    provider = FakeTranslationProvider()
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: provider,
    )
    ctx = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path), target_lang="zh-CN"),
        pages=[
            Page(
                page_id="p001",
                bubbles=[
                    Bubble(
                        bubble_id="b1",
                        source_text="おはようございます。",
                        speaker_name="灯里",
                    ),
                ],
            )
        ],
        memory_context={"character_profiles": {}, "page_profiles": {}},
    )

    result = TranslationStage().execute(ctx)

    assert len(result.translations) == 1
    assert "character_memory" in result.artifacts
    assert result.artifacts["character_memory"] == []
    assert StateManager.list_characters(tmp_path) == []
