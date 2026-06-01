"""Tests for OCR-first text and Vision enrichment separation."""

from __future__ import annotations

import json
from pathlib import Path

from mga.models import Bubble, Page, PageImage, ProjectConfig, TranslationCandidate, VisualFootnote
from mga.pipeline.render_stage import RenderStage
from mga.pipeline.stages import PipelineContext
from mga.models.translation import SemanticTranslation
from mga.pipeline.translation_stage import (
    _build_persona_render_prompt,
    _build_semantic_translation_prompt,
    _build_translation_prompt,
)
from mga.pipeline.vision_stage import OCRArtifactStage, VisionEnrichmentStage


class FakeVisionProvider:
    def vision_structured(self, messages, images, schema):
        return {
            "scene_summary": "A quiet hallway.",
            "bubbles": [
                {
                    "bubble_id": "region-0000-0000",
                    "source_text": "WRONG",
                    "reading_order": 0,
                    "box_type": "dialogue",
                    "provisional_speaker": "girl-near-door",
                    "voice_hint": "polite, hesitant",
                    "tone": "worried",
                }
            ],
            "visual_footnotes": [
                {
                    "source_text": "保健室",
                    "translation_hint": "医务室",
                    "kind": "sign",
                }
            ],
            "voice_hints": ["girl-near-door speaks politely"],
        }


def test_ocr_artifact_text_remains_authoritative_with_vision_enrichment(tmp_path, monkeypatch):
    payload = tmp_path / "payload"
    payload.mkdir()
    (payload / "pages.json").write_text(
        json.dumps([{"page_index": 0, "artifact": "artifact-0000.json"}]),
        encoding="utf-8",
    )
    (payload / "artifact-0000.json").write_text(
        json.dumps({
            "text_regions": [
                {
                    "text": "大丈夫？",
                    "lines": [[[10, 10], [60, 10], [60, 40], [10, 40]]],
                }
            ]
        }),
        encoding="utf-8",
    )

    page = Page(page_id="page_0000", page_index=0, image=PageImage(path=__file__))
    ctx = PipelineContext(
        project_config=ProjectConfig(),
        pages=[page],
        metadata={"artifact_payload_dir": str(payload)},
    )

    ctx = OCRArtifactStage().execute(ctx)
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: FakeVisionProvider(),
    )
    ctx = VisionEnrichmentStage().execute(ctx)

    bubble = ctx.pages[0].bubbles[0]
    assert bubble.source_text == "大丈夫？"
    assert bubble.provisional_speaker == "girl-near-door"
    assert bubble.voice_hint == "polite, hesitant"
    assert bubble.tone == "worried"
    assert ctx.pages[0].visual_footnotes[0].translation_hint == "医务室"


def test_translation_prompt_includes_vision_hints_without_profile():
    prompt = _build_translation_prompt(
        source_text="大丈夫？",
        memory_ctx={},
        cultural_ctx={},
        target_lang="zh-CN",
        vision_ctx={
            "provisional_speaker": "girl-near-door",
            "voice_hint": "polite, hesitant",
            "box_type": "dialogue",
            "page_voice_hints": ["girl-near-door speaks politely"],
        },
    )

    assert "Vision 补充提示" in prompt
    assert "临时说话人：girl-near-door" in prompt
    assert "polite, hesitant" in prompt


def test_semantic_and_persona_prompts_keep_vision_roles_separate():
    vision_ctx = {
        "provisional_speaker": "girl-near-door",
        "voice_hint": "polite, hesitant",
        "box_type": "dialogue",
        "page_voice_hints": ["girl-near-door speaks politely"],
    }

    semantic_prompt = _build_semantic_translation_prompt(
        "大丈夫？",
        {},
        "zh-CN",
        vision_ctx=vision_ctx,
    )
    persona_prompt = _build_persona_render_prompt(
        "大丈夫？",
        SemanticTranslation(bubble_id="b1", text="没事吧？"),
        {},
        "zh-CN",
        vision_ctx=vision_ctx,
    )

    assert "## Semantic Translation" in semantic_prompt
    assert "临时说话人" not in semantic_prompt
    assert "polite, hesitant" not in semantic_prompt
    assert "文本框类型：dialogue" in semantic_prompt
    assert "## Persona Rendering" in persona_prompt
    assert "临时说话人：girl-near-door" in persona_prompt
    assert "polite, hesitant" in persona_prompt


def test_render_stage_writes_visual_footnotes(tmp_path):
    payload = tmp_path / "payload"
    payload.mkdir()
    page = Page(page_id="page_0000", page_index=0)
    page.bubbles.append(Bubble(bubble_id="region-0000-0000", source_text="大丈夫？"))
    page.visual_footnotes.append(
        VisualFootnote(source_text="保健室", translation_hint="医务室", kind="sign")
    )
    ctx = PipelineContext(
        project_config=ProjectConfig(target_lang="zh-CN"),
        pages=[page],
        translations=[TranslationCandidate(bubble_id="region-0000-0000", text="你没事吧？")],
    )

    RenderStage()._write_page_translations(payload, ctx, ctx.project_config, 0)

    data = json.loads((payload / "translations-0000.json").read_text(encoding="utf-8"))
    assert data["translations"][0]["translation"] == "你没事吧？"
    assert data["footnotes"] == [
        {
            "original": "保健室",
            "translation": "医务室",
            "type": "visual",
            "kind": "sign",
        }
    ]
