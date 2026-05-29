"""Integration coverage for page-sequential character memory in TranslationStage."""

from __future__ import annotations

import json

from mga.memory.state import StateManager
from mga.models import Bubble, Page, ProjectConfig
from mga.pipeline.stages import PipelineContext
from mga.pipeline.translation_stage import TranslationStage


class RecordingTranslationProvider:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def chat(self, messages):
        prompt = messages[-1]["content"]
        self.prompts.append(prompt)
        if "## Persona Rendering" in prompt:
            if "礼貌、克制" in prompt:
                text = "请您稍等一下。"
                moves = ["polite_formality"]
            elif "粗鲁、直接" in prompt:
                text = "少废话，快点。"
                moves = ["rough_directness"]
            else:
                text = "好的。"
                moves = []
            return json.dumps({
                "text": text,
                "persona_moves": moves,
                "rationale": "persona render",
                "confidence": 0.9,
            }, ensure_ascii=False)
        return json.dumps({
            "text": "好的。",
            "speech_act": "statement",
            "emotion": "neutral",
            "must_preserve": [],
            "footnotes": [],
            "rationale": "semantic draft",
            "confidence": 0.8,
        }, ensure_ascii=False)


def test_translation_stage_updates_memory_between_pages(tmp_path, monkeypatch):
    provider = RecordingTranslationProvider()
    monkeypatch.setattr(
        "mga.pipeline.translation_stage.get_provider",
        lambda name, **settings: provider,
    )

    context = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path), target_lang="zh-CN"),
        pages=[
            Page(
                page_id="p001",
                bubbles=[
                    Bubble(
                        bubble_id="p001-b001",
                        source_text="おはようございます。",
                        speaker_id="akari",
                    ),
                    Bubble(
                        bubble_id="p001-b002",
                        source_text="そんなの知るかよ。",
                        speaker_id="ren",
                    ),
                    Bubble(
                        bubble_id="p001-b003",
                        source_text="はい。",
                    ),
                ],
            ),
            Page(
                page_id="p002",
                bubbles=[
                    Bubble(
                        bubble_id="p002-b001",
                        source_text="ありがとうございます。",
                        speaker_id="akari",
                    ),
                    Bubble(
                        bubble_id="p002-b002",
                        source_text="早くしろ。",
                        speaker_id="ren",
                    ),
                    Bubble(
                        bubble_id="p002-b003",
                        source_text="これは誰？",
                        provisional_speaker="unknown-girl",
                    ),
                ],
            ),
        ],
        memory_context={"character_profiles": {}, "page_profiles": {}},
    )

    result = TranslationStage().execute(context)

    assert len(result.translations) == 6
    assert len(provider.prompts) == 12
    assert provider.prompts[0].startswith("## Semantic Translation")
    assert provider.prompts[1].startswith("## Persona Rendering")
    assert "角色档案" not in provider.prompts[0]
    assert "角色档案" not in provider.prompts[1]

    dialogue = result.artifacts["translation"]["dialogue_realization"]
    assert dialogue["version"] == "translation_graph_v0_a"
    assert dialogue["semantic_count"] == 6
    assert dialogue["persona_count"] == 6
    assert len(dialogue["entries"]) == 6
    assert dialogue["entries"][0]["semantic"]["text"] == "好的。"
    assert dialogue["entries"][0]["persona"]["rendered_text"] == "好的。"
    assert dialogue["entries"][3]["persona"]["memory_context_used"] is True
    assert dialogue["entries"][5]["speaker_id"] is None
    assert dialogue["entries"][5]["provisional_speaker"] == "unknown-girl"

    akari = StateManager.get_character(tmp_path, "akari")
    ren = StateManager.get_character(tmp_path, "ren")
    unknown = StateManager.get_character(tmp_path, "unknown-girl")

    assert akari is not None
    assert akari.tone_spectrum["observed_style"] == "礼貌、克制、句尾偏正式"
    assert ren is not None
    assert ren.tone_spectrum["observed_style"] == "粗鲁、直接、句尾偏口语"
    assert unknown is None

    p002_akari_semantic = provider.prompts[6]
    p002_akari_persona = provider.prompts[7]
    p002_ren_semantic = provider.prompts[8]
    p002_ren_persona = provider.prompts[9]

    assert p002_akari_semantic.startswith("## Semantic Translation")
    assert "角色档案" not in p002_akari_semantic
    assert p002_akari_persona.startswith("## Persona Rendering")
    assert "角色档案" in p002_akari_persona
    assert "礼貌、克制、句尾偏正式" in p002_akari_persona
    assert "粗鲁、直接、句尾偏口语" not in p002_akari_persona
    assert p002_ren_semantic.startswith("## Semantic Translation")
    assert "角色档案" not in p002_ren_semantic
    assert "粗鲁、直接、句尾偏口语" in p002_ren_persona
    assert "礼貌、克制、句尾偏正式" not in p002_ren_persona

    trace = result.artifacts["character_memory"]
    assert [item["bubble_id"] for item in trace] == [
        "p001-b001",
        "p001-b002",
        "p002-b001",
        "p002-b002",
    ]
    assert trace[0]["memory_before"] == {}
    assert trace[2]["memory_before"]["tone_spectrum"]["observed_style"] == (
        "礼貌、克制、句尾偏正式"
    )
    assert trace[2]["memory_after"]["speech_patterns"]["latest_source_sample"] == (
        "ありがとうございます。"
    )
    assert "Source: ありがとうございます。" in trace[2]["prompt_excerpt"]

    assert result.memory_context["page_profiles"]["p002"]["akari"]["tone_spectrum"][
        "observed_style"
    ] == "礼貌、克制、句尾偏正式"
    assert result.memory_context["page_profiles"]["p002"]["ren"]["tone_spectrum"][
        "observed_style"
    ] == "粗鲁、直接、句尾偏口语"
