"""Tests for QAStage repair behavior."""

from __future__ import annotations

from mga.models import Bubble, Page, ProjectConfig, TranslationCandidate
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
