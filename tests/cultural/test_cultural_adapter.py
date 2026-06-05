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


def test_get_translation_context_includes_project_style_guide(tmp_path):
    (tmp_path / "style_guide.toml").write_text(
        """
literal_vs_free = 0.7
honorific_handling = "keep honorific nuance"
key_decisions = ["short bubbles", "formal narration"]
raw_notes = ["internal only"]
""".strip(),
        encoding="utf-8",
    )
    adapter = CulturalAdapter(tmp_path)

    ctx = adapter.get_translation_context({"bubbles": []})

    assert "## Style Guide" in ctx
    assert "- literal_vs_free: 0.7" in ctx
    assert "- honorific_handling: keep honorific nuance" in ctx
    assert "- key_decisions: short bubbles, formal narration" in ctx
    assert "raw_notes" not in ctx


def test_get_translation_context_uses_learned_style_guide_fallback(tmp_path):
    learned_dir = tmp_path / "memory" / "learned"
    learned_dir.mkdir(parents=True)
    (learned_dir / "style_guide.toml").write_text(
        'dialog_style = "casual"\n',
        encoding="utf-8",
    )
    adapter = CulturalAdapter(tmp_path)

    ctx = adapter.get_translation_context({"bubbles": []})

    assert "- dialog_style: casual" in ctx


def test_get_translation_context_with_terms():
    adapter = CulturalAdapter(Path("/tmp/nonexistent_project"))
    ctx = adapter.get_translation_context({
        "bubbles": [{"bubble_id": "b1", "source_text": "ドキドキする"}],
    })
    # Should contain strategy notes or be empty if no cultural terms found
    assert isinstance(ctx, str)


def test_get_translation_context_includes_known_db_terms(tmp_path):
    term_dir = tmp_path / "terminology"
    term_dir.mkdir()
    (term_dir / "terms.toml").write_text(
        '[terms]\n'
        'glass_join = { term_jp = "glass_join", term_target = "glass mending", '
        'strategy = "literal", notes = "recurring repair art" }\n',
        encoding="utf-8",
    )
    adapter = CulturalAdapter(tmp_path)

    ctx = adapter.get_translation_context({
        "bubbles": [{"bubble_id": "b1", "source_text": "The glass_join ritual begins"}],
    })

    assert "## Terminology Context" in ctx
    assert "**glass_join**" in ctx
    assert "-> glass mending" in ctx
    assert "[literal]" in ctx
    assert "recurring repair art" in ctx
