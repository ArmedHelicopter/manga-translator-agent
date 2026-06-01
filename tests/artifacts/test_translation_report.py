"""Tests for TranslationReport build and write."""

import json
from dataclasses import asdict

from mga.artifacts.translation_report import (
    TranslationEntry,
    TranslationReport,
    build_translation_report,
    write_translation_report,
)
from mga.artifacts.store import ArtifactStore
from mga.models import Bubble, Page, TranslationCandidate
from mga.pipeline.stages import PipelineContext


def _make_context(
    pages: list[Page] | None = None,
    translations: list[TranslationCandidate] | None = None,
    qa_report: dict | None = None,
    artifacts: dict | None = None,
) -> PipelineContext:
    ctx = PipelineContext()
    ctx.pages = pages or []
    ctx.translations = translations or []
    ctx.qa_report = qa_report or {}
    ctx.artifacts = artifacts or {}
    return ctx


def test_build_translation_report_basic():
    pages = [
        Page(page_id="p1", page_index=0, bubbles=[
            Bubble(bubble_id="b1", source_text="太郎は学校に行った"),
            Bubble(bubble_id="b2", source_text="花子は本を読んだ"),
        ]),
    ]
    translations = [
        TranslationCandidate(bubble_id="b1", text="太郎去了学校", confidence=0.95, rationale="direct"),
        TranslationCandidate(bubble_id="b2", text="花子在看书", confidence=0.88, rationale="natural"),
    ]
    ctx = _make_context(pages=pages, translations=translations)
    report = build_translation_report(ctx)

    assert len(report.entries) == 2
    assert report.summary["total_translations"] == 2
    assert report.summary["pages_needing_human_review"] == 0
    assert report.summary["entries_needing_human_review"] == 0
    assert 0.8 < report.summary["avg_confidence"] < 1.0

    # Verify page_id association
    entry = next(e for e in report.entries if e.bubble_id == "b1")
    assert entry.page_id == "p1"
    assert entry.source_text == "太郎は学校に行った"
    assert entry.translated_text == "太郎去了学校"


def test_translation_entry_includes_dialogue_realization_trace():
    pages = [
        Page(page_id="p1", page_index=0, bubbles=[
            Bubble(bubble_id="b1", source_text="よろしく"),
        ]),
    ]
    translations = [
        TranslationCandidate(bubble_id="b1", text="拜托啦。", confidence=0.9),
    ]
    artifacts = {
        "translation": {
            "dialogue_realization": {
                "entries": [
                    {
                        "bubble_id": "b1",
                        "speaker_id": "ren",
                        "semantic": {
                            "text": "拜托了。",
                            "rationale": "semantic meaning",
                        },
                        "persona": {
                            "persona_moves": ["rough_directness"],
                            "rationale": "rendered as Ren",
                        },
                    }
                ]
            }
        }
    }

    ctx = _make_context(pages=pages, translations=translations, artifacts=artifacts)
    report = build_translation_report(ctx)

    entry = report.entries[0]
    assert entry.speaker_id == "ren"
    assert entry.semantic_text == "拜托了。"
    assert entry.semantic_rationale == "semantic meaning"
    assert entry.persona_moves == ["rough_directness"]
    assert entry.persona_rationale == "rendered as Ren"


def test_translation_entry_exposes_provider_trace_and_cascade_errors():
    pages = [
        Page(page_id="p1", page_index=0, bubbles=[
            Bubble(bubble_id="b1", source_text="よろしく"),
        ]),
    ]
    translations = [
        TranslationCandidate(bubble_id="b1", text="拜托啦。", confidence=0.9),
    ]
    semantic_trace = {
        "operation": "semantic_translation",
        "role": "fallback",
        "provider": "fallback-llm",
        "model": "fallback-model",
    }
    persona_trace = {
        "operation": "persona_rendering",
        "role": "fallback",
        "provider": "fallback-llm",
        "model": "fallback-model",
    }
    cascade_error = {
        "bubble_id": "b1",
        "operation": "semantic_translation",
        "role": "primary",
        "provider": "primary-llm",
        "error": "primary down",
        "type": "RuntimeError",
    }
    artifacts = {
        "translation": {
            "dialogue_realization": {
                "entries": [
                    {
                        "bubble_id": "b1",
                        "provider": {
                            "semantic": semantic_trace,
                            "persona": persona_trace,
                        },
                    }
                ]
            },
            "provider_cascade_errors": [cascade_error],
        }
    }

    ctx = _make_context(pages=pages, translations=translations, artifacts=artifacts)
    report = build_translation_report(ctx)

    entry = report.entries[0]
    assert entry.provider_trace == {
        "semantic": semantic_trace,
        "persona": persona_trace,
    }
    assert entry.provider_cascade_errors == [cascade_error]
    assert report.summary["provider_cascade_errors_total"] == 1


def test_translation_entry_qa_findings_association():
    pages = [
        Page(page_id="p1", page_index=0, bubbles=[
            Bubble(bubble_id="b1", source_text="src1"),
        ]),
    ]
    translations = [
        TranslationCandidate(bubble_id="b1", text="tgt1", confidence=0.6),
    ]
    qa_report = {
        "findings": [
            {"bubble_id": "b1", "severity": "warning", "message": "low confidence"},
            {"bubble_id": "b1", "severity": "info", "message": "style note"},
        ],
    }
    ctx = _make_context(pages=pages, translations=translations, qa_report=qa_report)
    report = build_translation_report(ctx)

    entry = report.entries[0]
    assert len(entry.qa_findings) == 2
    assert entry.needs_human_review is True  # confidence < 0.7
    assert report.summary["pages_needing_human_review"] == 1
    assert report.summary["entries_needing_human_review"] == 1


def test_translation_entry_needs_review_critical():
    pages = [
        Page(page_id="p1", page_index=0, bubbles=[
            Bubble(bubble_id="b1", source_text="src"),
        ]),
    ]
    translations = [
        TranslationCandidate(bubble_id="b1", text="tgt", confidence=0.95),
    ]
    qa_report = {
        "findings": [
            {"bubble_id": "b1", "severity": "critical", "message": "wrong translation"},
        ],
    }
    ctx = _make_context(pages=pages, translations=translations, qa_report=qa_report)
    report = build_translation_report(ctx)

    entry = report.entries[0]
    assert entry.needs_human_review is True  # critical severity


def test_translation_report_summary():
    pages = [
        Page(page_id="p1", page_index=0, bubbles=[
            Bubble(bubble_id="b1", source_text="s1"),
            Bubble(bubble_id="b2", source_text="s2"),
        ]),
    ]
    translations = [
        TranslationCandidate(bubble_id="b1", text="t1", confidence=0.9),
        TranslationCandidate(bubble_id="b2", text="t2", confidence=0.5),
    ]
    qa_report = {
        "findings": [
            {"bubble_id": "b2", "severity": "warning", "message": "check"},
        ],
    }
    ctx = _make_context(pages=pages, translations=translations, qa_report=qa_report)
    report = build_translation_report(ctx)

    assert report.summary["total_translations"] == 2
    assert report.summary["pages_needing_human_review"] == 1
    assert report.summary["qa_findings_total"] == 1


def test_write_translation_report(tmp_path):
    store = ArtifactStore(tmp_path)
    report = TranslationReport(
        entries=[
            TranslationEntry(
                bubble_id="b1", page_id="p1", source_text="src",
                translated_text="tgt", confidence=0.9, rationale="ok",
            ),
        ],
        summary={"total_translations": 1},
    )
    rel = write_translation_report(store, report)
    assert rel == "translation-report.json"
    content = json.loads((tmp_path / "translation-report.json").read_text(encoding="utf-8"))
    assert len(content["entries"]) == 1
    assert content["entries"][0]["bubble_id"] == "b1"
    assert content["summary"]["total_translations"] == 1


def test_empty_context():
    ctx = _make_context()
    report = build_translation_report(ctx)
    assert len(report.entries) == 0
    assert report.summary["total_translations"] == 0
    assert report.summary["avg_confidence"] == 0.0
