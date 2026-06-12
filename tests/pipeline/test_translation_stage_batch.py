"""Tests for batch-parallel translation stage routing."""

from __future__ import annotations

import threading
import pytest

from mga.models import (
    Bubble,
    Page,
    ProjectConfig,
    ProviderRoute,
    StageProviderConfig,
)
from mga.pipeline.stages import PipelineContext
from mga.pipeline.translation_stage import TranslationStage


class BatchParallelProvider:
    def chat(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        if prompt.startswith("## Semantic Translation"):
            source = prompt.rsplit("Source:", 1)[-1].splitlines()[0].strip()
            return (
                '{"text":"semantic:' + source + '","speech_act":"statement",'
                '"emotion":"calm","must_preserve":[],"footnotes":[],'
                '"rationale":"ok","confidence":0.9}'
            )
        return (
            '{"text":"final","persona_moves":["naturalize"],'
            '"rationale":"ok","confidence":0.9}'
        )


def test_batch_parallel_processes_batches_in_order(tmp_path, monkeypatch) -> None:
    """Batch-parallel should process pages in batches and maintain order."""
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: BatchParallelProvider(),
    )

    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={
                "parallel_mode": "batch-parallel",
                "batch_size": 2,
                "max_concurrent_requests": 2,
                "semantic_timeout": 30,
            },
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[Bubble(bubble_id="p1_b1", source_text="page1", reading_order=0)],
            ),
            Page(
                page_id="p2",
                bubbles=[Bubble(bubble_id="p2_b1", source_text="page2", reading_order=0)],
            ),
            Page(
                page_id="p3",
                bubbles=[Bubble(bubble_id="p3_b1", source_text="page3", reading_order=0)],
            ),
        ],
    )

    result = TranslationStage().execute(ctx)

    assert len(result.translations) == 3
    assert [t.bubble_id for t in result.translations] == ["p1_b1", "p2_b1", "p3_b1"]
    assert result.artifacts["translation"]["parallel_mode"] == "batch-parallel"


def test_batch_parallel_memory_consistency_across_batches(tmp_path, monkeypatch) -> None:
    """Memory updates should accumulate serially by page_id order within and across batches."""
    memory_updates = []
    update_lock = threading.Lock()

    class MemoryTrackingProvider:
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if prompt.startswith("## Semantic Translation"):
                return (
                    '{"text":"semantic","speech_act":"statement",'
                    '"emotion":"calm","must_preserve":[],"footnotes":[],'
                    '"rationale":"ok","confidence":0.9}'
                )
            return (
                '{"text":"final","persona_moves":[],'
                '"rationale":"ok","confidence":0.9}'
            )

    from mga.memory.character_memory_updater import CharacterMemoryUpdater
    original_update = CharacterMemoryUpdater.update_from_translation

    def tracked_update(self, *args, **kwargs):
        with update_lock:
            speaker = args[0] if args else kwargs.get("speaker")
            page_id = args[2] if len(args) > 2 else kwargs.get("page_id")
            memory_updates.append({"speaker": speaker, "page_id": page_id})
        return original_update(self, *args, **kwargs)

    monkeypatch.setattr(
        "mga.memory.character_memory_updater.CharacterMemoryUpdater.update_from_translation",
        tracked_update,
    )
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: MemoryTrackingProvider(),
    )

    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={
                "parallel_mode": "batch-parallel",
                "batch_size": 2,
                "max_concurrent_requests": 2,
            },
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(bubble_id="p1_b1", source_text="text", reading_order=0, speaker_id="alice"),
                ],
            ),
            Page(
                page_id="p2",
                bubbles=[
                    Bubble(bubble_id="p2_b1", source_text="text", reading_order=0, speaker_id="alice"),
                ],
            ),
            Page(
                page_id="p3",
                bubbles=[
                    Bubble(bubble_id="p3_b1", source_text="text", reading_order=0, speaker_id="alice"),
                ],
            ),
        ],
    )

    result = TranslationStage().execute(ctx)

    assert len(result.translations) == 3
    # Memory updates should be in page order: p1, p2, p3
    assert len(memory_updates) >= 3
    page_order = [u["page_id"] for u in memory_updates if u["speaker"] == "alice"]
    assert page_order == ["p1", "p2", "p3"]


def test_batch_parallel_fallback_on_error(tmp_path, monkeypatch) -> None:
    """Batch-parallel should fallback to serial on ParallelExecutionError."""
    from mga.pipeline.parallel_executor import ParallelExecutionError

    call_count = {"batch": 0, "serial": 0}

    class FallbackProvider:
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if prompt.startswith("## Semantic Translation"):
                call_count["batch"] += 1
                if call_count["batch"] == 2:
                    raise RuntimeError("Simulated batch failure")
                return (
                    '{"text":"semantic","speech_act":"statement",'
                    '"emotion":"calm","must_preserve":[],"footnotes":[],'
                    '"rationale":"ok","confidence":0.9}'
                )
            call_count["serial"] += 1
            return (
                '{"text":"serial_fallback","persona_moves":[],'
                '"rationale":"ok","confidence":0.9}'
            )

    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: FallbackProvider(),
    )

    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={
                "parallel_mode": "batch-parallel",
                "batch_size": 2,
            },
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[Bubble(bubble_id="b1", source_text="text", reading_order=0)],
            ),
            Page(
                page_id="p2",
                bubbles=[Bubble(bubble_id="b2", source_text="text", reading_order=0)],
            ),
        ],
    )

    result = TranslationStage().execute(ctx)

    assert len(result.translations) == 2
    assert all(t.text == "serial_fallback" for t in result.translations)
    assert "parallel_mode" not in result.artifacts["translation"]


def test_batch_parallel_config_parsing(tmp_path, monkeypatch) -> None:
    """Batch-parallel should respect batch_size config."""
    batch_tracking = {"batches": []}
    batch_lock = threading.Lock()

    class BatchSizeTrackingProvider:
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if prompt.startswith("## Semantic Translation"):
                return (
                    '{"text":"semantic","speech_act":"statement",'
                    '"emotion":"calm","must_preserve":[],"footnotes":[],'
                    '"rationale":"ok","confidence":0.9}'
                )
            return (
                '{"text":"final","persona_moves":[],'
                '"rationale":"ok","confidence":0.9}'
            )

    from mga.pipeline.translation_stage import TranslationStage
    original_execute_batch = TranslationStage._execute_batch_parallel

    def tracked_execute_batch(self, *args, **kwargs):
        parallel_config = kwargs.get("parallel_config", {})
        batch_size = parallel_config.get("batch_size", 3)
        context = kwargs.get("context") or (args[0] if args else None)
        num_pages = len(context.pages) if context else 0
        expected_batches = (num_pages + batch_size - 1) // batch_size

        with batch_lock:
            batch_tracking["batches"].append({
                "batch_size": batch_size,
                "num_pages": num_pages,
                "expected_batches": expected_batches,
            })

        return original_execute_batch(self, *args, **kwargs)

    monkeypatch.setattr(
        "mga.pipeline.translation_stage.TranslationStage._execute_batch_parallel",
        tracked_execute_batch,
    )
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: BatchSizeTrackingProvider(),
    )

    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={
                "parallel_mode": "batch-parallel",
                "batch_size": 2,
            },
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(page_id=f"p{i}", bubbles=[Bubble(bubble_id=f"b{i}", source_text="text", reading_order=0)])
            for i in range(5)
        ],
    )

    result = TranslationStage().execute(ctx)

    assert len(result.translations) == 5
    assert len(batch_tracking["batches"]) == 1
    tracked = batch_tracking["batches"][0]
    assert tracked["batch_size"] == 2
    assert tracked["num_pages"] == 5
    assert tracked["expected_batches"] == 3  # ceil(5/2) = 3 batches
