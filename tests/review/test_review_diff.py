from __future__ import annotations

import json
from pathlib import Path

import pytest

from mga.models import TranslationCandidate
from mga.review import build_translation_diff, compare_translations


def test_compare_translations_reports_changed_added_and_removed_bubbles() -> None:
    original = [
        TranslationCandidate(bubble_id="b1", text="old text"),
        TranslationCandidate(bubble_id="b2", text="removed text"),
        TranslationCandidate(bubble_id="b3", text="same text"),
    ]
    revised = [
        TranslationCandidate(bubble_id="b1", text="new text"),
        TranslationCandidate(bubble_id="b3", text="same text"),
        TranslationCandidate(bubble_id="b4", text="added text"),
    ]

    report = compare_translations(original, revised)

    assert report["total_bubbles"] == 4
    assert report["changed_bubbles"] == 3
    assert report["change_ratio"] == 0.75
    assert [
        (change["bubble_id"], change["change_type"])
        for change in report["changes"]
    ] == [
        ("b1", "changed"),
        ("b2", "removed"),
        ("b4", "added"),
    ]


def test_build_translation_diff_loads_wrapped_translation_payloads(tmp_path: Path) -> None:
    original_path = tmp_path / "original.json"
    revised_path = tmp_path / "revised.json"
    original_path.write_text(
        json.dumps({"translations": [{"bubble_id": "b1", "text": "old"}]}),
        encoding="utf-8",
    )
    revised_path.write_text(
        json.dumps({"candidates": [{"bubble_id": "b1", "text": "new"}]}),
        encoding="utf-8",
    )

    report = build_translation_diff(original_path, revised_path)

    assert report["changed_bubbles"] == 1
    assert report["changes"][0]["original"] == "old"
    assert report["changes"][0]["revised"] == "new"


def test_build_translation_diff_loads_translation_report_entries(tmp_path: Path) -> None:
    original_path = tmp_path / "original-report.json"
    revised_path = tmp_path / "revised-report.json"
    original_path.write_text(
        json.dumps(
            {
                "entries": [
                    {"bubble_id": "b1", "source_text": "src", "translated_text": "old"},
                    {"bubble_id": "b2", "source_text": "src2", "translated_text": "same"},
                ],
                "summary": {"total_translations": 2},
            }
        ),
        encoding="utf-8",
    )
    revised_path.write_text(
        json.dumps(
            {
                "entries": [
                    {"bubble_id": "b1", "source_text": "src", "translated_text": "new"},
                    {"bubble_id": "b2", "source_text": "src2", "translated_text": "same"},
                ],
                "summary": {"total_translations": 2},
            }
        ),
        encoding="utf-8",
    )

    report = build_translation_diff(original_path, revised_path)

    assert report["total_bubbles"] == 2
    assert report["changed_bubbles"] == 1
    assert report["changes"][0]["bubble_id"] == "b1"
    assert report["changes"][0]["original"] == "old"
    assert report["changes"][0]["revised"] == "new"


def test_build_translation_diff_preserves_translation_report_review_context(tmp_path: Path) -> None:
    original_path = tmp_path / "original-report.json"
    revised_path = tmp_path / "revised-report.json"
    original_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "bubble_id": "b1",
                        "page_id": "p1",
                        "source_text": "src",
                        "translated_text": "old",
                        "confidence": 0.91,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    revised_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "bubble_id": "b1",
                        "page_id": "p1",
                        "source_text": "src",
                        "speaker_id": "ren",
                        "translated_text": "new",
                        "confidence": 0.62,
                        "needs_human_review": True,
                        "qa_findings": [
                            {
                                "bubble_id": "b1",
                                "feedback_type": "warning",
                                "message": "voice drift",
                            }
                        ],
                        "repair_plan": [
                            {
                                "bubble_id": "b1",
                                "target": "persona",
                                "action": "repair_persona_rendering",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    report = build_translation_diff(original_path, revised_path)

    change = report["changes"][0]
    assert change["page_id"] == "p1"
    assert change["source_text"] == "src"
    assert change["speaker_id"] == "ren"
    assert change["original_confidence"] == 0.91
    assert change["revised_confidence"] == 0.62
    assert change["needs_human_review"] is True
    assert change["qa_findings"][0]["message"] == "voice drift"
    assert change["repair_plan"][0]["target"] == "persona"


def test_build_translation_diff_rejects_malformed_translation_report_entries(tmp_path: Path) -> None:
    original_path = tmp_path / "original-report.json"
    revised_path = tmp_path / "revised-report.json"
    original_path.write_text(
        json.dumps({"entries": ["not an entry"]}),
        encoding="utf-8",
    )
    revised_path.write_text(
        json.dumps({"entries": [{"bubble_id": "b1", "translated_text": "new"}]}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="translation report entries"):
        build_translation_diff(original_path, revised_path)
