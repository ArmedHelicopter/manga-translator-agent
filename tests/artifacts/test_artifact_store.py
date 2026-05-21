"""Tests for extended ArtifactStore methods."""

import json
from pathlib import Path

from mga.artifacts.store import ArtifactStore


def test_write_run_summary(tmp_path):
    store = ArtifactStore(tmp_path)
    payload = {"timestamp": "2026-01-01T00:00:00Z", "status": "completed", "page_count": 5}
    rel = store.write_run_summary(payload)
    assert rel == "run.json"
    content = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert content["status"] == "completed"
    assert content["page_count"] == 5


def test_write_qa_report(tmp_path):
    store = ArtifactStore(tmp_path)
    payload = {"passed": True, "total_findings": 0}
    rel = store.write_qa_report(payload)
    assert rel == "qa_report.json"
    content = json.loads((tmp_path / "qa_report.json").read_text(encoding="utf-8"))
    assert content["passed"] is True


def test_write_translation_report(tmp_path):
    store = ArtifactStore(tmp_path)
    payload = {
        "entries": [{"bubble_id": "b1", "translated_text": "hello"}],
        "summary": {"total_translations": 1},
    }
    rel = store.write_translation_report(payload)
    assert rel == "translation-report.json"
    content = json.loads((tmp_path / "translation-report.json").read_text(encoding="utf-8"))
    assert len(content["entries"]) == 1
    assert content["summary"]["total_translations"] == 1
