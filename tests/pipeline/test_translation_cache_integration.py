"""Tests for LLMCache integration in TranslationStage (Experiment #12 Round 3)."""

from __future__ import annotations

import json
from pathlib import Path

from mga.models import Bubble, Page, ProjectConfig, ProviderRoute, StageProviderConfig
from mga.pipeline.stages import PipelineContext
from mga.pipeline.translation_stage import TranslationStage


class CacheTrackingProvider:
    """Counts LLM calls to verify cache hit/miss behavior."""

    def __init__(self) -> None:
        self.call_count = 0

    def chat(self, messages, **kwargs):
        self.call_count += 1
        prompt = messages[-1]["content"]
        if prompt.startswith("## Semantic Translation"):
            source = prompt.rsplit("Source:", 1)[-1].splitlines()[0].strip()
            return json.dumps({
                "text": f"semantic:{source}",
                "speech_act": "statement",
                "emotion": "calm",
                "must_preserve": [],
                "footnotes": [],
                "rationale": "ok",
                "confidence": 0.9,
            })
        return json.dumps({
            "text": "final",
            "persona_moves": ["naturalize"],
            "rationale": "ok",
            "confidence": 0.9,
        })


def test_cache_hit_skips_llm_call(tmp_path, monkeypatch) -> None:
    """Second translation of same text should use cache, not call LLM."""
    provider = CacheTrackingProvider()
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: provider,
    )

    from mga.cache import LLMCache
    cache = LLMCache(cache_dir=str(tmp_path / ".cache"), enabled=True)

    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[Bubble(bubble_id="b1", source_text="hello world", reading_order=0)],
            )
        ],
    )
    ctx.llm_cache = cache

    # First call — cache miss
    result1 = TranslationStage().execute(ctx)
    first_call_count = provider.call_count
    assert first_call_count == 2, f"Expected 2 LLM calls (semantic+persona), got {first_call_count}"
    assert result1.translations[0].text == "final"

    # Second call with same text — cache hit
    ctx2 = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[Bubble(bubble_id="b1", source_text="hello world", reading_order=0)],
            )
        ],
    )
    ctx2.llm_cache = cache

    result2 = TranslationStage().execute(ctx2)
    # Both semantic and persona should be cached — 0 new LLM calls
    assert provider.call_count == first_call_count, (
        f"Expected no new LLM calls (cache hit), but got {provider.call_count - first_call_count}"
    )
    assert result2.translations[0].text == "final"

    cache_stats = cache.get_stats()
    assert cache_stats["hits"] >= 2, f"Expected >=2 cache hits, got {cache_stats['hits']}"
    cache.close()


def test_different_text_cache_miss(tmp_path, monkeypatch) -> None:
    """Different source text should miss cache and call LLM."""
    provider = CacheTrackingProvider()
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: provider,
    )

    from mga.cache import LLMCache
    cache = LLMCache(cache_dir=str(tmp_path / ".cache"), enabled=True)

    def run_translation(source_text: str):
        ctx = PipelineContext(
            project_config=ProjectConfig(
                working_dir=str(tmp_path),
                target_lang="zh-CN",
                provider_routes={
                    "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
                },
            ),
            pages=[
                Page(
                    page_id="p1",
                    bubbles=[Bubble(bubble_id="b1", source_text=source_text, reading_order=0)],
                )
            ],
        )
        ctx.llm_cache = cache
        return TranslationStage().execute(ctx)

    run_translation("text one")
    calls_after_first = provider.call_count
    assert calls_after_first == 2

    run_translation("text two")
    # Different text — should miss cache and call LLM again
    assert provider.call_count == calls_after_first + 2

    cache.close()


def test_cache_disabled_passes_through(tmp_path, monkeypatch) -> None:
    """When cache is disabled, every call hits LLM."""
    provider = CacheTrackingProvider()
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: provider,
    )

    from mga.cache import LLMCache
    cache = LLMCache(cache_dir=str(tmp_path / ".cache"), enabled=False)

    def run_translation():
        ctx = PipelineContext(
            project_config=ProjectConfig(
                working_dir=str(tmp_path),
                target_lang="zh-CN",
                provider_routes={
                    "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
                },
            ),
            pages=[
                Page(
                    page_id="p1",
                    bubbles=[Bubble(bubble_id="b1", source_text="same text", reading_order=0)],
                )
            ],
        )
        ctx.llm_cache = cache
        return TranslationStage().execute(ctx)

    run_translation()
    first_count = provider.call_count

    run_translation()
    # Cache disabled — should call LLM again
    assert provider.call_count == first_count * 2

    cache.close()


def test_no_cache_context_still_works(tmp_path, monkeypatch) -> None:
    """TranslationStage works without cache (context.llm_cache = None)."""
    provider = CacheTrackingProvider()
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: provider,
    )

    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[Bubble(bubble_id="b1", source_text="no cache", reading_order=0)],
            )
        ],
    )
    # No llm_cache set (default None)
    assert ctx.llm_cache is None

    result = TranslationStage().execute(ctx)
    assert len(result.translations) == 1
    assert provider.call_count == 2  # semantic + persona
