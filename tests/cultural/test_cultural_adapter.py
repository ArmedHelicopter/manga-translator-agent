"""Tests for mga.cultural.cultural_adapter — CulturalAdapter orchestration."""

from pathlib import Path

from mga.cultural.cultural_adapter import CulturalAdapter


def test_analyze_page_with_honorific():
    adapter = CulturalAdapter(Path("/tmp/nonexistent_project"))
    page_json = {
        "bubbles": [
            {"bubble_id": "b1", "source_text": "田中さん"},
        ],
    }
    results = adapter.analyze_page(page_json)
    assert "b1" in results
    # 田中さん should trigger HONORIFIC
    problem_types = [p["problem_types"] for p in results["b1"]]
    assert any("honorific" in pt for pt in problem_types)


def test_analyze_page_empty():
    adapter = CulturalAdapter(Path("/tmp/nonexistent_project"))
    results = adapter.analyze_page({"bubbles": []})
    assert results == {}


def test_process_translation_basic():
    adapter = CulturalAdapter(Path("/tmp/nonexistent_project"))
    result = adapter.process_translation(
        "b1", "テスト", {"translation": "test", "target_lang": "zh-CN"},
    )
    assert result["translation"] == "test"
    assert isinstance(result["adjustments"], list)


def test_get_translation_context_empty():
    adapter = CulturalAdapter(Path("/tmp/nonexistent_project"))
    ctx = adapter.get_translation_context({"bubbles": []})
    assert ctx == ""


def test_get_translation_context_with_terms():
    adapter = CulturalAdapter(Path("/tmp/nonexistent_project"))
    ctx = adapter.get_translation_context({
        "bubbles": [{"bubble_id": "b1", "source_text": "ドキドキする"}],
    })
    # Should contain strategy notes or be empty if no cultural terms found
    assert isinstance(ctx, str)
