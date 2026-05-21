"""Tests for relationship context injection in translation_stage."""

from mga.pipeline.translation_stage import _build_translation_prompt


# ---------------------------------------------------------------------------
# _build_translation_prompt tests
# ---------------------------------------------------------------------------

def test_prompt_with_relationship_ctx():
    prompt = _build_translation_prompt(
        source_text="おはよう",
        memory_ctx={},
        cultural_ctx={},
        target_lang="zh",
        relationship_ctx="关系上下文：tanaka→sato，礼貌",
    )
    assert "关系上下文" in prompt
    assert "tanaka→sato" in prompt
    assert "Source: おはよう" in prompt
    assert "zh" in prompt


def test_prompt_without_relationship_ctx():
    prompt = _build_translation_prompt(
        source_text="こんにちは",
        memory_ctx={},
        cultural_ctx={},
        target_lang="zh",
    )
    assert "关系上下文" not in prompt
    assert "Source: こんにちは" in prompt


def test_prompt_relationship_ctx_empty_string():
    """Empty string for relationship_ctx should not add a section."""
    prompt = _build_translation_prompt(
        source_text="やあ",
        memory_ctx={},
        cultural_ctx={},
        target_lang="zh",
        relationship_ctx="",
    )
    assert "关系上下文" not in prompt


def test_prompt_full_profile_with_relationship():
    """All sections present: memory profile, relationship, cultural, source."""
    memory_ctx = {
        "name_jp": "田中",
        "name_zh": "田中",
        "archetype": "hero",
        "speech_patterns": {"だ": "男性随意", "ですよ": "礼貌"},
        "catchphrases": ["絶対に諦めない"],
        "tone_spectrum": {"battle": "激昂"},
        "translation_notes": {"だ": "不要翻译为'だよ'"},
    }
    cultural_ctx = {
        "translation_context": "文化注释：日本学校场景",
    }
    prompt = _build_translation_prompt(
        source_text="行くぜ！",
        memory_ctx=memory_ctx,
        cultural_ctx=cultural_ctx,
        target_lang="zh",
        relationship_ctx="关系上下文：语气=礼貌",
    )

    # Character profile section
    assert "角色档案" in prompt
    assert "田中" in prompt
    assert "hero" in prompt
    assert "男性随意" in prompt
    assert "絶対に諦めない" in prompt
    assert "激昂" in prompt
    assert "不要翻译为" in prompt

    # Relationship section
    assert "关系上下文" in prompt
    assert "礼貌" in prompt

    # Cultural section
    assert "文化注释" in prompt

    # Source
    assert "Source: 行くぜ！" in prompt


def test_prompt_with_cultural_no_relationship():
    """Cultural context without relationship."""
    prompt = _build_translation_prompt(
        source_text="おはよう",
        memory_ctx={},
        cultural_ctx={"translation_context": "学校场景"},
        target_lang="zh",
    )
    assert "学校场景" in prompt
    assert "关系上下文" not in prompt


def test_prompt_minimal():
    """Minimal input — only source text and target lang."""
    prompt = _build_translation_prompt(
        source_text="test",
        memory_ctx={},
        cultural_ctx={},
        target_lang="en",
    )
    assert "Translate" in prompt
    assert "en" in prompt
    assert "Source: test" in prompt
    assert "JSON" in prompt or "json" in prompt


def test_prompt_memory_partial_fields():
    """Memory context with only some fields populated."""
    memory_ctx = {
        "name_jp": "花子",
        "catchphrases": ["もう！", "やるね"],
    }
    prompt = _build_translation_prompt(
        source_text="やあ",
        memory_ctx=memory_ctx,
        cultural_ctx={},
        target_lang="zh",
    )
    assert "花子" in prompt
    assert "もう！" in prompt
    assert "やるね" in prompt
    # archetype and speech_patterns not present
    assert "原型" not in prompt
    assert "语言模式" not in prompt
