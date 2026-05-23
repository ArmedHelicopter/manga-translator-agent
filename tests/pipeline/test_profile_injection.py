"""Tests for mga.pipeline.translation_stage — _build_translation_prompt."""

from mga.pipeline.translation_stage import _build_translation_prompt


# ── Full profile ───────────────────────────────────────────────


def test_prompt_with_full_profile():
    """Verify all profile sections appear in output."""
    memory_ctx = {
        "name_jp": "田中",
        "name_zh": "田中",
        "archetype": "detective",
        "speech_patterns": {"だ": "的", "よ": "哦"},
        "catchphrases": ["事件は必ず解決する"],
        "tone_spectrum": {"serious": "严肃", "playful": "俏皮"},
        "translation_notes": {"honorific": "保留"},
    }

    result = _build_translation_prompt("元気ですか？", memory_ctx, {}, "zh")

    assert "角色档案" in result
    assert "田中" in result
    assert "detective" in result
    assert "だ=的" in result
    assert "事件は必ず解決する" in result
    assert "严肃" in result
    assert "保留" in result
    assert "Source: 元気ですか？" in result
    assert "Return a JSON" in result


# ── Minimal profile ────────────────────────────────────────────


def test_prompt_with_minimal_profile():
    """Only name_jp and name_zh present."""
    memory_ctx = {
        "name_jp": "花子",
        "name_zh": "花子",
    }

    result = _build_translation_prompt("ありがとう", memory_ctx, {}, "zh")

    assert "角色档案" in result
    assert "花子" in result
    # Optional sections should not appear
    assert "原型" not in result
    assert "语言模式" not in result
    assert "口头禅" not in result
    assert "Source: ありがとう" in result


# ── No profile ─────────────────────────────────────────────────


def test_prompt_without_profile():
    """No memory_ctx (empty dict) still produces valid prompt."""
    result = _build_translation_prompt("おはよう", {}, {}, "zh")

    # Should not contain profile section
    assert "角色档案" not in result
    assert "Source: おはよう" in result
    assert "Return a JSON" in result


# ── Cultural context ───────────────────────────────────────────


def test_prompt_with_cultural_context():
    """cultural_ctx with translation_context is included."""
    cultural_ctx = {
        "translation_context": "此场景为正式商务场合，使用敬语。",
    }

    result = _build_translation_prompt("お疲れ様です", {}, cultural_ctx, "zh")

    assert "此场景为正式商务场合" in result
    assert "Source: お疲れ様です" in result


# ── Structure ──────────────────────────────────────────────────


def test_prompt_structure():
    """Output contains required structural sections."""
    memory_ctx = {
        "name_jp": "太郎",
        "name_zh": "太郎",
        "archetype": "少年",
    }

    result = _build_translation_prompt("よろしく", memory_ctx, {}, "zh")

    assert "角色档案" in result
    assert "Source: よろしく" in result
    assert "Return a JSON" in result
    # Verify it asks for text and rationale keys
    assert "'text'" in result
    assert "'rationale'" in result
