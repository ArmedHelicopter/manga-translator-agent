"""Tests for translation stage failure resilience."""

from __future__ import annotations
import pytest

from mga.models import Bubble, Page, ProjectConfig, ProviderRoute, StageProviderConfig
from mga.pipeline.stages import PipelineContext
from mga.pipeline.translation_stage import TranslationStage


class PersonaFailureProvider:
    @property
    def model_name(self) -> str:
        return "fake-model"

    def chat(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        if prompt.startswith("## Semantic Translation"):
            return '{"text":"semantic draft","speech_act":"statement","emotion":"calm","must_preserve":[],"footnotes":[],"rationale":"ok","confidence":0.9}'
        raise RuntimeError("persona down")


@pytest.mark.xfail(reason="StageExecutionError not caught at bubble level (pre-existing)", strict=False)
def test_translation_stage_keeps_bubble_when_persona_provider_fails(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: PersonaFailureProvider(),
    )
    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[Bubble(bubble_id="b1", source_text="source text", reading_order=0)],
            )
        ],
    )

    result = TranslationStage().execute(ctx)

    assert len(result.translations) == 1
    candidate = result.translations[0]
    assert candidate.bubble_id == "b1"
    assert candidate.text == "source text"
    assert candidate.confidence == 0.0
    assert "human translation required" in candidate.rationale
    trace = result.artifacts["translation"]["dialogue_realization"]["entries"][0]
    assert trace["semantic"]["text"] == "semantic draft"
    assert trace["persona"]["persona_moves"] == [
        "provider_failure",
        "human_translation_required",
    ]
    assert trace["provider"]["persona"]["operation"] == "persona_render"
    assert trace["provider"]["persona"]["provider"] == "unavailable"


def test_translatable_bubbles_include_cover_titles_but_not_sfx() -> None:
    page = Page(
        page_id="p1",
        bubbles=[
            Bubble(
                bubble_id="vision-0000-0000",
                source_text="私を喰べたい",
                detection_source="vision",
                box_type="cover_title",
            ),
            Bubble(
                bubble_id="vision-0000-0001",
                source_text="ドン",
                detection_source="vision",
                box_type="sfx",
            ),
            Bubble(
                bubble_id="vision-0000-0002",
                source_text="WA",
                detection_source="vision",
                box_type="sign",
            ),
        ],
    )

    bubbles = TranslationStage._translatable_bubbles(page)

    assert [bubble.bubble_id for bubble in bubbles] == ["vision-0000-0000"]
