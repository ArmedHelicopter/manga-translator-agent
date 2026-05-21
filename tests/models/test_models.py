"""Tests for mga.models — page, translation, and project config models."""

from mga.models import (
    BoundingBox,
    Bubble,
    Page,
    PageImage,
    TranslationCandidate,
    ProjectConfig,
    ProviderRoute,
    StageProviderConfig,
)


def test_bubble_defaults():
    b = Bubble()
    assert b.bubble_id == ""
    assert b.source_text == ""
    assert b.speaker_id is None
    assert b.tone is None
    assert b.bbox.width == 0.0


def test_page_construction():
    img = PageImage(path="/tmp/test.png", width=800, height=1200)
    page = Page(page_id="p1", page_index=0, image=img)
    assert page.page_id == "p1"
    assert page.image.path == "/tmp/test.png"
    assert page.bubbles == []
    assert page.source_lang == "ja"


def test_translation_candidate():
    tc = TranslationCandidate(
        bubble_id="b1", text="你好", rationale="Direct translation",
    )
    assert tc.bubble_id == "b1"
    assert tc.text == "你好"


def test_project_config_defaults():
    cfg = ProjectConfig()
    assert cfg.source_lang == "ja"
    assert cfg.target_lang == "zh-CN"
    assert cfg.output_format == "images"
    assert cfg.provider_routes == {}


def test_project_config_provider_routes():
    stage_cfg = StageProviderConfig(primary=ProviderRoute(provider="openai", model="gpt-4"))
    cfg = ProjectConfig(provider_routes={"vision": stage_cfg})
    assert cfg.provider_routes["vision"].primary.provider == "openai"
