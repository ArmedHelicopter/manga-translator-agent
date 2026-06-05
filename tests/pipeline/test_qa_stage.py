"""Tests for QAStage repair behavior."""

from __future__ import annotations

from mga.models import Bubble, Page, ProjectConfig, TranslationCandidate
from mga.memory.entities import CharacterState
from mga.memory.state import StateManager
from mga.pipeline.character_stage import CharacterAttributionStage
from mga.pipeline.qa_stage import QAStage
from mga.pipeline.stages import PipelineContext
from mga.qa.base import QAFeedback, QAFeedbackType


def test_qa_retranslate_uses_original_bubble_source_and_records_provider_trace(monkeypatch):
    captured: dict[str, object] = {}

    class FakeOrchestrator:
        def proofread(self, page, translations, memory_context):
            return [
                QAFeedback(
                    bubble_id="b1",
                    feedback_type=QAFeedbackType.ERROR,
                    category="fact",
                    message="wrong fact",
                )
            ]

        def group_by_bubble(self, feedbacks):
            return {"b1": feedbacks}

    class FakeProvider:
        def chat(self, messages, **kwargs):
            captured["prompt"] = messages[-1]["content"]
            return "修正后的译文"

    def fake_get_provider(name, **settings):
        captured["provider_name"] = name
        return FakeProvider()

    monkeypatch.setattr("mga.pipeline.qa_stage.QAOrchestrator", lambda: FakeOrchestrator())
    monkeypatch.setattr("mga.providers.cascade.get_provider", fake_get_provider)

    ctx = PipelineContext(
        project_config=ProjectConfig(),
        pages=[
            Page(
                page_id="p1",
                bubbles=[Bubble(bubble_id="b1", source_text="原文だよ")],
            )
        ],
        translations=[TranslationCandidate(bubble_id="b1", text="错误旧译")],
    )

    result = QAStage().execute(ctx)

    assert "Source: 原文だよ" in captured["prompt"]
    assert "Source: 错误旧译" not in captured["prompt"]
    assert "Previous translation: 错误旧译" in captured["prompt"]
    assert result.translations[0].text == "修正后的译文"
    assert result.qa_report["findings"][0]["bubble_id"] == "b1"
    assert result.qa_report["provider_cascade_calls"] == [
        {
            "bubble_id": "b1",
            "operation": "qa_retranslate",
            "role": "primary",
            "provider": "openai",
            "model": "",
        }
    ]


def test_qa_stage_surfaces_character_consistency_findings_from_memory_context():
    ctx = PipelineContext(
        project_config=ProjectConfig(),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(
                        bubble_id="b1",
                        source_text="signature attack",
                        speaker_id="akari",
                    )
                ],
            )
        ],
        translations=[TranslationCandidate(bubble_id="b1", text="plain attack")],
        memory_context={
            "character_profiles": {
                "akari": {
                    "catchphrases": ["signature"],
                }
            }
        },
    )

    result = QAStage().execute(ctx)

    categories = {finding["category"] for finding in result.qa_report["findings"]}
    assert "character.catchphrase_missing" in categories
    assert result.qa_report["passed"] is False


def test_qa_stage_uses_recent_translation_history_loaded_by_character_stage(tmp_path):
    profile_dir = tmp_path / "character_profiles"
    profile_dir.mkdir()
    (profile_dir / "akari.toml").write_text(
        """
[meta]
character_id = "akari"
name_jp = "Akari"
""".strip(),
        encoding="utf-8",
    )
    translations_dir = tmp_path / "translations"
    translations_dir.mkdir()
    (translations_dir / "p001.json").write_text(
        """
{
  "page_id": "p001",
  "bubbles": [
    {"bubble_id": "old1", "speaker_id": "akari"},
    {"bubble_id": "old2", "speaker_id": "akari"}
  ],
  "translations": [
    {"bubble_id": "old1", "text": "ok"},
    {"bubble_id": "old2", "text": "hi"}
  ]
}
""".strip(),
        encoding="utf-8",
    )
    ctx = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path)),
        pages=[
            Page(
                page_id="p002",
                bubbles=[
                    Bubble(
                        bubble_id="new1",
                        source_text="SOURCE",
                        speaker_id="akari",
                    )
                ],
            )
        ],
        translations=[
            TranslationCandidate(
                bubble_id="new1",
                text="this translation is much longer than the recent voice samples",
            )
        ],
    )

    ctx = CharacterAttributionStage().execute(ctx)
    result = QAStage().execute(ctx)

    categories = {finding["category"] for finding in result.qa_report["findings"]}
    assert ctx.memory_context["recent_translations"] == {"akari": ["ok", "hi"]}
    assert "character.voice_drift" in categories


def test_qa_stage_uses_voice_evolution_context_loaded_by_character_stage(tmp_path):
    StateManager.upsert_character(
        tmp_path,
        CharacterState(
            character_id="akari",
            name_jp="Akari",
            voice_evolutions=[
                {
                    "adopt_at_chapter": 8,
                    "old_patterns": ["old-honorific"],
                    "new_pattern": "new-honorific",
                },
            ],
        ),
    )
    ctx = PipelineContext(
        project_config=ProjectConfig(working_dir=str(tmp_path)),
        pages=[
            Page(
                page_id="p008",
                bubbles=[
                    Bubble(
                        bubble_id="b1",
                        source_text="old-honorific request",
                        speaker_id="akari",
                    )
                ],
            )
        ],
        translations=[TranslationCandidate(bubble_id="b1", text="plain request")],
        metadata={"chapter": 8},
    )

    ctx = CharacterAttributionStage().execute(ctx)
    result = QAStage().execute(ctx)

    assert ctx.memory_context["chapter_number"] == 8
    assert ctx.memory_context["voice_evolutions"] == {
        "akari": [
            {
                "adopt_at_chapter": 8,
                "old_patterns": ["old-honorific"],
                "new_pattern": "new-honorific",
            },
        ],
    }
    categories = {finding["category"] for finding in result.qa_report["findings"]}
    assert "evolution.missing_new_pattern" in categories


def test_qa_stage_includes_profile_warnings_in_report():
    ctx = PipelineContext(
        project_config=ProjectConfig(),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(
                        bubble_id="b1",
                        source_text="SOURCE",
                    )
                ],
            )
        ],
        translations=[TranslationCandidate(bubble_id="b1", text="translation")],
        memory_context={
            "profile_warnings": [
                {
                    "category": "character.profile_stale",
                    "character_id": "akari",
                    "message": "Character profile for akari is stale",
                }
            ]
        },
    )

    result = QAStage().execute(ctx)

    assert result.qa_report["passed"] is False
    assert result.qa_report["total_findings"] == 1
    assert result.qa_report["findings"] == [
        {
            "feedback_type": "warning",
            "category": "character.profile_stale",
            "bubble_id": "",
            "message": "Character profile for akari is stale",
            "confidence": 1.0,
            "original_text": "",
            "suggested_text": "",
            "rationale": "Profile maintenance warning",
            "character_id": "akari",
        }
    ]


def test_qa_stage_builds_repair_plan_for_semantic_persona_and_layout(monkeypatch):
    class FakeOrchestrator:
        def proofread(self, page, translations, memory_context):
            return [
                QAFeedback(
                    bubble_id="b1",
                    feedback_type=QAFeedbackType.WARNING,
                    category="fact.number_mismatch",
                    message="wrong number",
                    confidence=0.82,
                    original_text="old number",
                    suggested_text="new number",
                    rationale="number should match source",
                ),
                QAFeedback(
                    bubble_id="b1",
                    feedback_type=QAFeedbackType.WARNING,
                    category="character.relationship_speech_missing",
                    message="missing address",
                    confidence=0.74,
                    original_text="plain line",
                    suggested_text="addressed line",
                    rationale="relationship speech is required",
                ),
                QAFeedback(
                    bubble_id="b1",
                    feedback_type=QAFeedbackType.SUGGESTION,
                    category="style.overflow_risk",
                    message="too long",
                    confidence=0.66,
                    original_text="long line",
                    suggested_text="short line",
                    rationale="fit the bubble",
                ),
            ]

        def group_by_bubble(self, feedbacks):
            return {"b1": feedbacks}

    monkeypatch.setattr("mga.pipeline.qa_stage.QAOrchestrator", lambda: FakeOrchestrator())

    ctx = PipelineContext(
        project_config=ProjectConfig(),
        pages=[
            Page(
                page_id="p1",
                bubbles=[Bubble(bubble_id="b1", source_text="SOURCE")],
            )
        ],
        translations=[TranslationCandidate(bubble_id="b1", text="translation")],
    )

    result = QAStage().execute(ctx)

    assert result.qa_report["repair_plan"] == [
        {
            "bubble_id": "b1",
            "category": "fact.number_mismatch",
            "feedback_type": "warning",
            "target": "semantic",
            "action": "repair_semantic_translation",
            "message": "wrong number",
            "confidence": 0.82,
            "original_text": "old number",
            "suggested_text": "new number",
            "rationale": "number should match source",
        },
        {
            "bubble_id": "b1",
            "category": "character.relationship_speech_missing",
            "feedback_type": "warning",
            "target": "persona",
            "action": "repair_persona_rendering",
            "message": "missing address",
            "confidence": 0.74,
            "original_text": "plain line",
            "suggested_text": "addressed line",
            "rationale": "relationship speech is required",
        },
        {
            "bubble_id": "b1",
            "category": "style.overflow_risk",
            "feedback_type": "suggestion",
            "target": "layout",
            "action": "repair_layout_fit",
            "message": "too long",
            "confidence": 0.66,
            "original_text": "long line",
            "suggested_text": "short line",
            "rationale": "fit the bubble",
        },
    ]
    assert result.artifacts["qa"]["repair_plan"] == result.qa_report["repair_plan"]


def test_qa_stage_surfaces_default_cultural_qa_findings_and_semantic_repair_route():
    ctx = PipelineContext(
        project_config=ProjectConfig(),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(
                        bubble_id="b1",
                        source_text="Tanaka\u3055\u3093, are you well?",
                    )
                ],
            )
        ],
        translations=[TranslationCandidate(bubble_id="b1", text="Tanaka, how are you")],
    )

    result = QAStage().execute(ctx)

    cultural_findings = [
        finding
        for finding in result.qa_report["findings"]
        if finding["category"] == "cultural.honorific_removed"
    ]
    assert cultural_findings
    assert result.qa_report["passed"] is False
    assert any(
        item["category"] == "cultural.honorific_removed"
        and item["target"] == "semantic"
        and item["action"] == "repair_semantic_translation"
        for item in result.qa_report["repair_plan"]
    )


def test_qa_stage_passes_page_cultural_analysis_to_cultural_qa():
    ctx = PipelineContext(
        project_config=ProjectConfig(),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(
                        bubble_id="b1",
                        source_text="GLASSJOIN activates",
                    )
                ],
            )
        ],
        translations=[
            TranslationCandidate(
                bubble_id="b1",
                text="The repair art activates",
            )
        ],
    )
    ctx.cultural_context = {
        "p1": {
            "analysis": {
                "b1": [
                    {
                        "term": "GLASSJOIN",
                        "strategy": "preserve",
                    }
                ]
            }
        }
    }

    result = QAStage().execute(ctx)

    assert any(
        finding["category"] == "cultural.strategy_inconsistent"
        for finding in result.qa_report["findings"]
    )
    assert any(
        item["category"] == "cultural.strategy_inconsistent"
        and item["target"] == "semantic"
        for item in result.qa_report["repair_plan"]
    )
