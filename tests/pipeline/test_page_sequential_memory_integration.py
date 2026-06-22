"""Integration coverage for page-sequential character memory in TranslationStage."""

from __future__ import annotations

import json

from mga.memory.entities import CharacterState
from mga.memory.graph import CharacterGraph
from mga.memory.state import StateManager
from mga.models import Bubble, Page, ProjectConfig
from mga.pipeline.character_stage import CharacterAttributionStage
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
        "mga.providers.cascade.get_provider",
        lambda name, **settings: provider,
    )

    context = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={"parallel_mode": "serial"},
        ),
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


def test_translation_stage_injects_saved_relationship_graph_context(tmp_path, monkeypatch):
    graph = CharacterGraph()
    graph.add_relationship(
        "akari",
        "ren",
        relationship="mentor",
        formality="formal",
        honorific="sensei",
    )
    graph.save(tmp_path)

    provider = RecordingTranslationProvider()
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: provider,
    )

    context = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={"parallel_mode": "serial"},
        ),
        pages=[
            Page(
                page_id="p001",
                bubbles=[
                    Bubble(
                        bubble_id="p001-b001",
                        source_text="SOURCE_A",
                        speaker_id="akari",
                    ),
                    Bubble(
                        bubble_id="p001-b002",
                        source_text="SOURCE_B",
                        speaker_id="ren",
                    ),
                ],
            ),
        ],
        memory_context={"character_profiles": {}, "page_profiles": {}},
    )

    result = TranslationStage().execute(context)

    assert len(provider.prompts) == 4
    akari_persona_prompt = provider.prompts[1]
    assert akari_persona_prompt.startswith("## Persona Rendering")
    assert "mentor" in akari_persona_prompt
    assert "sensei" in akari_persona_prompt
    assert "- listener_id: ren" in akari_persona_prompt

    first_trace = result.artifacts["translation"]["dialogue_realization"]["entries"][0]
    assert first_trace["speaker_id"] == "akari"
    assert first_trace["persona"]["listener_id"] == "ren"
    assert first_trace["persona"]["relationship_context_used"] is True


def test_translation_stage_uses_nearest_speaker_as_relationship_listener(
    tmp_path,
    monkeypatch,
):
    graph = CharacterGraph()
    graph.add_relationship(
        "akari",
        "mika",
        relationship="rival",
        formality="casual",
        honorific="chan",
    )
    graph.add_relationship(
        "akari",
        "ren",
        relationship="mentor",
        formality="formal",
        honorific="sensei",
    )
    graph.save(tmp_path)

    provider = RecordingTranslationProvider()
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
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
                        source_text="SOURCE_MIKA",
                        speaker_id="mika",
                        reading_order=0,
                    ),
                    Bubble(
                        bubble_id="p001-b002",
                        source_text="SOURCE_REN",
                        speaker_id="ren",
                        reading_order=1,
                    ),
                    Bubble(
                        bubble_id="p001-b003",
                        source_text="SOURCE_AKARI",
                        speaker_id="akari",
                        reading_order=2,
                    ),
                ],
            ),
        ],
        memory_context={"character_profiles": {}, "page_profiles": {}},
    )

    result = TranslationStage().execute(context)

    akari_persona_prompt = provider.prompts[5]
    assert "mentor" in akari_persona_prompt
    assert "sensei" in akari_persona_prompt
    assert "rival" not in akari_persona_prompt
    akari_trace = result.artifacts["translation"]["dialogue_realization"]["entries"][2]
    assert akari_trace["persona"]["listener_id"] == "ren"
    assert akari_trace["persona"]["relationship_context_used"] is True


def test_translation_stage_applies_honorific_compensation_from_relationship_context(
    tmp_path,
    monkeypatch,
):
    class HonorificProvider:
        def chat(self, messages):
            prompt = messages[-1]["content"]
            if "## Persona Rendering" in prompt:
                return json.dumps({
                    "text": "\u4f60\u662f\u8c01",
                    "persona_moves": [],
                    "rationale": "persona render",
                    "confidence": 0.9,
                }, ensure_ascii=False)
            return json.dumps({
                "text": "semantic draft",
                "speech_act": "question",
                "emotion": "neutral",
                "must_preserve": [],
                "footnotes": [],
                "rationale": "semantic draft",
                "confidence": 0.8,
            }, ensure_ascii=False)

    graph = CharacterGraph()
    graph.add_relationship(
        "akari",
        "ren",
        relationship="teacher",
        formality="formal",
        honorific="sensei",
    )
    graph.save(tmp_path)

    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: HonorificProvider(),
    )

    context = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path), target_lang="zh-CN"),
        pages=[
            Page(
                page_id="p001",
                bubbles=[
                    Bubble(
                        bubble_id="p001-b001",
                        source_text="SOURCE_A",
                        speaker_id="akari",
                    ),
                    Bubble(
                        bubble_id="p001-b002",
                        source_text="SOURCE_B",
                        speaker_id="ren",
                    ),
                ],
            ),
        ],
        memory_context={
            "character_profiles": {
                "akari": {"status": "junior", "in_group": True},
                "ren": {"status": "senior", "in_group": True},
            },
            "page_profiles": {
                "p001": {
                    "akari": {"status": "junior", "in_group": True},
                    "ren": {"status": "senior", "in_group": True},
                },
            },
        },
    )

    result = TranslationStage().execute(context)

    assert result.translations[0].text == "\u60a8\u662f\u8c01"
    first_trace = result.artifacts["translation"]["dialogue_realization"]["entries"][0]
    assert first_trace["final_text"] == "\u60a8\u662f\u8c01"
    assert first_trace["persona"]["rendered_text"] == "\u60a8\u662f\u8c01"
    assert first_trace["persona"]["relationship_context_used"] is True


def test_translation_stage_injects_listener_specific_profile_speech_rules(tmp_path, monkeypatch):
    graph = CharacterGraph()
    graph.add_relationship(
        "akari",
        "ren",
        relationship="mentor",
        formality="formal",
        honorific="sensei",
    )
    graph.save(tmp_path)

    provider = RecordingTranslationProvider()
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: provider,
    )

    context = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={"parallel_mode": "serial"},
        ),
        pages=[
            Page(
                page_id="p001",
                bubbles=[
                    Bubble(
                        bubble_id="p001-b001",
                        source_text="SOURCE_A",
                        speaker_id="akari",
                    ),
                    Bubble(
                        bubble_id="p001-b002",
                        source_text="SOURCE_B",
                        speaker_id="ren",
                    ),
                ],
            ),
        ],
        memory_context={
            "character_profiles": {},
            "page_profiles": {
                "p001": {
                    "akari": {
                        "relationship_speech": {
                            "ren": {
                                "honorific_level": "polite",
                                "self_ref": "boku",
                                "address": "Sensei",
                                "sentence_style": "short polite sentences",
                            },
                        },
                    },
                },
            },
        },
    )

    TranslationStage().execute(context)

    akari_persona_prompt = provider.prompts[1]
    assert "## Relationship-specific speech rules" in akari_persona_prompt
    assert "- listener_id: ren" in akari_persona_prompt
    assert "- honorific_level: polite" in akari_persona_prompt
    assert "- self_ref: boku" in akari_persona_prompt
    assert "- address: Sensei" in akari_persona_prompt
    assert "- sentence_style: short polite sentences" in akari_persona_prompt


def test_translation_stage_injects_scene_memory_context(tmp_path, monkeypatch):
    provider = RecordingTranslationProvider()
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: provider,
    )

    context = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path), target_lang="zh-CN"),
        pages=[
            Page(
                page_id="p001",
                scene_summary="A short summary from the page adapter",
                bubbles=[
                    Bubble(
                        bubble_id="p001-b001",
                        source_text="SOURCE_A",
                        speaker_id="akari",
                    ),
                ],
            ),
        ],
        memory_context={
            "character_profiles": {},
            "page_profiles": {"p001": {}},
            "scene_contexts": {
                "p001": {
                    "scene_id": "ch1_p1_glass_room",
                    "mood": "tense",
                    "scene_description": "Akari confronts Ren in the glass room",
                    "narrative_summary": "Ren hides what happened in the previous chapter",
                    "relationship_changes": ["Akari stops trusting Ren"],
                    "key_dialogue": ["Tell me the truth."],
                    "future_impact": "Akari investigates alone next chapter",
                    "characters": [
                        {
                            "character_id": "akari",
                            "name_jp": "Akari",
                            "name_zh": "Deng",
                        }
                    ],
                },
            },
        },
    )

    result = TranslationStage().execute(context)

    persona_prompt = provider.prompts[1]
    assert "## Page Summary" in persona_prompt
    assert "A short summary from the page adapter" in persona_prompt
    assert "## Scene Memory" in persona_prompt
    assert "- scene_id: ch1_p1_glass_room" in persona_prompt
    assert "- mood: tense" in persona_prompt
    assert "- scene_description: Akari confronts Ren in the glass room" in persona_prompt
    assert "- narrative_summary: Ren hides what happened in the previous chapter" in persona_prompt
    assert "  - Akari stops trusting Ren" in persona_prompt
    assert "  - Tell me the truth." in persona_prompt
    assert "- future_impact: Akari investigates alone next chapter" in persona_prompt
    assert "  - akari / Akari / Deng" in persona_prompt
    trace = result.artifacts["translation"]["dialogue_realization"]["entries"][0]
    assert trace["persona"]["memory_context_used"] is True


def test_translation_stage_uses_relationship_speech_loaded_by_character_stage(
    tmp_path,
    monkeypatch,
):
    StateManager.upsert_character(
        tmp_path,
        CharacterState(
            character_id="akari",
            relationship_speech={
                "ren": {
                    "honorific_level": "polite",
                    "self_ref": "boku",
                    "address": "Ren-sensei",
                    "sentence_style": "short polite sentences",
                },
            },
        ),
    )
    StateManager.upsert_character(tmp_path, CharacterState(character_id="ren"))
    graph = CharacterGraph()
    graph.add_relationship(
        "akari",
        "ren",
        relationship="mentor",
        formality="formal",
        honorific="sensei",
    )
    graph.save(tmp_path)

    provider = RecordingTranslationProvider()
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: provider,
    )
    context = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={"parallel_mode": "serial"},
        ),
        pages=[
            Page(
                page_id="p001",
                bubbles=[
                    Bubble(
                        bubble_id="p001-b001",
                        source_text="SOURCE_A",
                        speaker_id="akari",
                    ),
                    Bubble(
                        bubble_id="p001-b002",
                        source_text="SOURCE_B",
                        speaker_id="ren",
                    ),
                ],
            ),
        ],
    )

    context = CharacterAttributionStage().execute(context)
    TranslationStage().execute(context)

    assert context.memory_context["page_profiles"]["p001"]["akari"][
        "relationship_speech"
    ]["ren"]["address"] == "Ren-sensei"
    akari_persona_prompt = provider.prompts[1]
    assert "## Relationship-specific speech rules" in akari_persona_prompt
    assert "- listener_id: ren" in akari_persona_prompt
    assert "- self_ref: boku" in akari_persona_prompt
    assert "- address: Ren-sensei" in akari_persona_prompt
    assert "- sentence_style: short polite sentences" in akari_persona_prompt


def test_translation_stage_prompt_includes_learned_style_guide(tmp_path, monkeypatch):
    (tmp_path / "style_guide.toml").write_text(
        """
literal_vs_free = 0.25
dialog_style = "concise"
""".strip(),
        encoding="utf-8",
    )
    provider = RecordingTranslationProvider()
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
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
                        source_text="SOURCE_A",
                    ),
                ],
            ),
        ],
    )

    context = CharacterAttributionStage().execute(context)
    TranslationStage().execute(context)

    semantic_prompt = provider.prompts[0]
    assert "## Style Guide" in semantic_prompt
    assert "- literal_vs_free: 0.25" in semantic_prompt
    assert "- dialog_style: concise" in semantic_prompt


def test_translation_stage_injects_translation_memory_context(tmp_path, monkeypatch):
    provider = RecordingTranslationProvider()
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: provider,
    )
    translations_dir = tmp_path / "translations"
    translations_dir.mkdir()
    (translations_dir / "p000.json").write_text(
        json.dumps(
            {
                "page_id": "p000",
                "bubbles": [
                    {
                        "bubble_id": "b0",
                        "source_text": "Where is the glass blade?",
                        "speaker_id": "akari",
                        "reading_order": 1,
                    }
                ],
                "translations": [
                    {
                        "bubble_id": "b0",
                        "text": "glass-blade-memory-zh",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    context = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path), target_lang="zh-CN"),
        pages=[
            Page(
                page_id="p001",
                bubbles=[
                    Bubble(
                        bubble_id="b1",
                        source_text="Where is the glass blade now?",
                        speaker_id="akari",
                    )
                ],
            )
        ],
        memory_context={"character_profiles": {}, "page_profiles": {}},
    )

    result = TranslationStage().execute(context)

    semantic_prompt = provider.prompts[0]
    assert "## Translation Memory" in semantic_prompt
    assert "source: Where is the glass blade?" in semantic_prompt
    assert "translation: glass-blade-memory-zh" in semantic_prompt
    trace = result.artifacts["translation"]["dialogue_realization"]["entries"][0]
    assert trace["persona"]["memory_context_used"] is True


def test_translation_stage_falls_back_to_secondary_provider(tmp_path, monkeypatch):
    class BrokenProvider:
        def chat(self, messages, **kwargs):
            raise RuntimeError("primary down")

    provider = RecordingTranslationProvider()

    def fake_get_provider(name, **settings):
        if name == "primary":
            return BrokenProvider()
        return provider

    monkeypatch.setattr("mga.providers.cascade.get_provider", fake_get_provider)

    from mga.models import ProviderRoute, StageProviderConfig

    context = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            provider_routes={
                "translation": StageProviderConfig(
                    primary=ProviderRoute(provider="primary"),
                    fallback=ProviderRoute(provider="fallback"),
                )
            },
        ),
        pages=[
            Page(
                page_id="p001",
                bubbles=[
                    Bubble(
                        bubble_id="p001-b001",
                        source_text="おはようございます。",
                        speaker_id="akari",
                    ),
                ],
            ),
        ],
        memory_context={"character_profiles": {}, "page_profiles": {}},
    )

    result = TranslationStage().execute(context)

    assert result.translations[0].text == "好的。"
    assert result.artifacts["translation"]["provider_cascade_errors"]
    assert result.artifacts["translation"]["provider_cascade_errors"][0]["provider"] == "primary"


def test_translation_stage_retains_source_for_low_confidence_persona(tmp_path, monkeypatch):
    class LowConfidenceProvider:
        def chat(self, messages):
            prompt = messages[-1]["content"]
            if "## Persona Rendering" in prompt:
                return json.dumps({
                    "text": "bad guess",
                    "persona_moves": [],
                    "rationale": "uncertain persona render",
                    "confidence": 0.4,
                })
            return json.dumps({
                "text": "semantic draft",
                "speech_act": "statement",
                "emotion": "neutral",
                "must_preserve": [],
                "footnotes": [],
                "rationale": "semantic draft",
                "confidence": 0.8,
            })

    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: LowConfidenceProvider(),
    )

    context = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path), target_lang="zh-CN"),
        pages=[
            Page(
                page_id="p001",
                bubbles=[
                    Bubble(
                        bubble_id="p001-b001",
                        source_text="SOURCE_ORIGINAL",
                        speaker_id="akari",
                    ),
                ],
            ),
        ],
        memory_context={"character_profiles": {}, "page_profiles": {}},
    )

    result = TranslationStage().execute(context)

    assert result.translations[0].text == "SOURCE_ORIGINAL"
    assert result.translations[0].confidence == 0.4
    assert "human translation required" in result.translations[0].rationale
    trace = result.artifacts["translation"]["dialogue_realization"]["entries"][0]
    assert trace["final_text"] == "SOURCE_ORIGINAL"
    assert trace["persona"]["rendered_text"] == "SOURCE_ORIGINAL"
    assert "human_translation_required" in trace["persona"]["persona_moves"]
    assert StateManager.get_character(tmp_path, "akari") is None
