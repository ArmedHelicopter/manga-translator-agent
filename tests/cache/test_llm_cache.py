"""Tests for the SQLite LLM cache."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mga.cache.llm_cache import LLMCache, _make_cache_key


class TestCacheKey:
    """Test deterministic cache key generation."""

    def test_same_input_same_key(self) -> None:
        k1 = _make_cache_key("hello", "semantic", "zh-CN", "gpt-4o")
        k2 = _make_cache_key("hello", "semantic", "zh-CN", "gpt-4o")
        assert k1 == k2

    def test_different_text_different_key(self) -> None:
        k1 = _make_cache_key("hello", "semantic", "zh-CN")
        k2 = _make_cache_key("world", "semantic", "zh-CN")
        assert k1 != k2

    def test_different_stage_different_key(self) -> None:
        k1 = _make_cache_key("hello", "semantic", "zh-CN")
        k2 = _make_cache_key("hello", "persona", "zh-CN")
        assert k1 != k2

    def test_different_lang_different_key(self) -> None:
        k1 = _make_cache_key("hello", "semantic", "zh-CN")
        k2 = _make_cache_key("hello", "semantic", "en")
        assert k1 != k2

    def test_different_model_different_key(self) -> None:
        k1 = _make_cache_key("hello", "semantic", "zh-CN", "gpt-4o")
        k2 = _make_cache_key("hello", "semantic", "zh-CN", "claude-3")
        assert k1 != k2

    def test_prompt_version_affects_key(self) -> None:
        k1 = _make_cache_key("hello", "semantic", "zh-CN", prompt_version="v1")
        k2 = _make_cache_key("hello", "semantic", "zh-CN", prompt_version="v2")
        assert k1 != k2


class TestLLMCache:
    """Test cache CRUD operations."""

    @pytest.fixture
    def cache(self, tmp_path: Path) -> LLMCache:
        return LLMCache(cache_dir=tmp_path / "cache", enabled=True)

    def test_put_and_get(self, cache: LLMCache) -> None:
        cache.put(
            source_text="こんにちは",
            stage="semantic_translation",
            target_lang="zh-CN",
            response='{"text": "你好"}',
            provider="openai",
            model="gpt-4o",
        )
        result = cache.get(
            source_text="こんにちは",
            stage="semantic_translation",
            target_lang="zh-CN",
            model="gpt-4o",
        )
        assert result == '{"text": "你好"}'

    def test_cache_miss_returns_none(self, cache: LLMCache) -> None:
        result = cache.get(
            source_text="nonexistent",
            stage="semantic",
            target_lang="zh-CN",
        )
        assert result is None

    def test_hit_count_increments(self, cache: LLMCache) -> None:
        cache.put(
            source_text="test",
            stage="semantic",
            target_lang="zh-CN",
            response="result",
        )
        cache.flush()  # Ensure data is written
        # Access 3 times
        for _ in range(3):
            cache.get(source_text="test", stage="semantic", target_lang="zh-CN")

        stats = cache.get_stats()
        assert stats["hits"] == 3
        assert stats["misses"] == 0

    def test_stats_track_misses(self, cache: LLMCache) -> None:
        cache.get(source_text="miss1", stage="s", target_lang="zh")
        cache.get(source_text="miss2", stage="s", target_lang="zh")
        stats = cache.get_stats()
        assert stats["misses"] == 2
        assert stats["hits"] == 0

    def test_overwrite_existing(self, cache: LLMCache) -> None:
        cache.put(
            source_text="test",
            stage="semantic",
            target_lang="zh-CN",
            response="old",
        )
        cache.flush()
        cache.put(
            source_text="test",
            stage="semantic",
            target_lang="zh-CN",
            response="new",
        )
        cache.flush()
        result = cache.get(
            source_text="test",
            stage="semantic",
            target_lang="zh-CN",
        )
        assert result == "new"

    def test_clear(self, cache: LLMCache) -> None:
        cache.put(
            source_text="test",
            stage="semantic",
            target_lang="zh-CN",
            response="result",
        )
        cache.flush()
        count = cache.clear()
        assert count == 1
        result = cache.get(
            source_text="test",
            stage="semantic",
            target_lang="zh-CN",
        )
        assert result is None

    def test_disabled_cache_returns_none(self, tmp_path: Path) -> None:
        cache = LLMCache(cache_dir=tmp_path / "cache", enabled=False)
        cache.put(
            source_text="test",
            stage="semantic",
            target_lang="zh-CN",
            response="result",
        )
        result = cache.get(
            source_text="test",
            stage="semantic",
            target_lang="zh-CN",
        )
        assert result is None

    def test_disabled_cache_put_is_noop(self, tmp_path: Path) -> None:
        cache = LLMCache(cache_dir=tmp_path / "cache", enabled=False)
        # Should not raise
        cache.put(
            source_text="test",
            stage="semantic",
            target_lang="zh-CN",
            response="result",
        )

    def test_stats_total_entries(self, cache: LLMCache) -> None:
        for i in range(5):
            cache.put(
                source_text=f"text_{i}",
                stage="semantic",
                target_lang="zh-CN",
                response=f"result_{i}",
            )
        cache.flush()
        stats = cache.get_stats()
        assert stats["total_entries"] == 5

    def test_context_manager(self, tmp_path: Path) -> None:
        with LLMCache(cache_dir=tmp_path / "cache", enabled=True) as cache:
            cache.put(
                source_text="test",
                stage="semantic",
                target_lang="zh-CN",
                response="result",
            )
            result = cache.get(
                source_text="test",
                stage="semantic",
                target_lang="zh-CN",
            )
            assert result == "result"

    def test_different_models_isolated(self, cache: LLMCache) -> None:
        """Cache entries for different models should not collide."""
        cache.put(
            source_text="test",
            stage="semantic",
            target_lang="zh-CN",
            response="gpt-result",
            model="gpt-4o",
        )
        cache.put(
            source_text="test",
            stage="semantic",
            target_lang="zh-CN",
            response="claude-result",
            model="claude-3",
        )
        assert cache.get(source_text="test", stage="semantic", target_lang="zh-CN", model="gpt-4o") == "gpt-result"
        assert cache.get(source_text="test", stage="semantic", target_lang="zh-CN", model="claude-3") == "claude-result"

    def test_unicode_source_text(self, cache: LLMCache) -> None:
        """Cache handles unicode source text correctly."""
        cache.put(
            source_text="こんにちは世界",
            stage="semantic",
            target_lang="zh-CN",
            response='{"text": "你好世界"}',
        )
        result = cache.get(
            source_text="こんにちは世界",
            stage="semantic",
            target_lang="zh-CN",
        )
        assert result == '{"text": "你好世界"}'


class TestLLMCacheThreadSafety:
    """Test cache under concurrent access."""

    def test_concurrent_put_get(self, tmp_path: Path) -> None:
        import threading

        cache = LLMCache(cache_dir=tmp_path / "cache", enabled=True)
        errors: list[Exception] = []

        def writer(n: int) -> None:
            try:
                for i in range(10):
                    cache.put(
                        source_text=f"thread_{n}_item_{i}",
                        stage="semantic",
                        target_lang="zh-CN",
                        response=f"result_{n}_{i}",
                    )
            except Exception as e:
                errors.append(e)

        def reader(n: int) -> None:
            try:
                for i in range(10):
                    cache.get(
                        source_text=f"thread_{n}_item_{i}",
                        stage="semantic",
                        target_lang="zh-CN",
                    )
            except Exception as e:
                errors.append(e)

        threads = []
        for n in range(4):
            threads.append(threading.Thread(target=writer, args=(n,)))
            threads.append(threading.Thread(target=reader, args=(n,)))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        cache.flush()  # Ensure all buffered writes are flushed
        assert len(errors) == 0
        stats = cache.get_stats()
        assert stats["total_entries"] == 40  # 4 threads * 10 items
