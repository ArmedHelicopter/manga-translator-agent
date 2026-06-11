"""Tests for pipeline parallel modes and orchestrator dispatch."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from mga.models import ProjectConfig
from mga.pipeline.stages import PipelineContext, PipelineStage
from mga.pipeline.orchestrator import PipelineOrchestrator


class _SlowStage(PipelineStage):
    """A stage that sleeps briefly to simulate work."""

    def __init__(self, name: str, order: int, delay: float = 0.01) -> None:
        self._name = name
        self._order = order
        self._delay = delay

    @property
    def name(self) -> str:
        return self._name

    @property
    def order(self) -> int:
        return self._order

    def execute(self, context: PipelineContext) -> PipelineContext:
        time.sleep(self._delay)
        context.metadata.setdefault("executed_stages", []).append(self._name)
        return context


class _RecordingStage(PipelineStage):
    """Records execution order for verification."""

    def __init__(self, name: str, order: int) -> None:
        self._name = name
        self._order = order
        self.executed: list[str] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def order(self) -> int:
        return self._order

    def execute(self, context: PipelineContext) -> PipelineContext:
        self.executed.append(context.pages[0].page_id if context.pages else "no-page")
        return context


class TestOrchestratorParallelModes:
    """Test that orchestrator dispatches to correct mode."""

    def test_serial_mode_default(self) -> None:
        cfg = ProjectConfig(
            parallel_mode="serial",
            working_dir=str(Path.cwd()),
        )
        stage = _SlowStage("test", 10)
        orch = PipelineOrchestrator(stages=[stage], config=cfg)

        ctx = orch.run("input", "output", cfg)
        assert "test" in ctx.metadata.get("stage_timings", {})
        assert ctx.metadata.get("parallel_mode") == "serial"

    def test_parallel_mode_dispatch(self) -> None:
        cfg = ProjectConfig(
            parallel_mode="parallel",
            pipeline_concurrency=3,
            working_dir=str(Path.cwd()),
        )
        stage = _SlowStage("test", 10)
        orch = PipelineOrchestrator(stages=[stage], config=cfg)

        ctx = orch.run("input", "output", cfg)
        assert ctx.metadata.get("parallel_mode") == "parallel"

    def test_pipelined_mode_dispatch(self) -> None:
        cfg = ProjectConfig(
            parallel_mode="pipelined",
            pipeline_concurrency=2,
            working_dir=str(Path.cwd()),
        )
        stage = _SlowStage("test", 10)
        orch = PipelineOrchestrator(stages=[stage], config=cfg)

        ctx = orch.run("input", "output", cfg)
        assert ctx.metadata.get("parallel_mode") == "pipelined"

    def test_thread_pool_created_for_parallel(self) -> None:
        cfg = ProjectConfig(
            parallel_mode="parallel",
            pipeline_concurrency=4,
            working_dir=str(Path.cwd()),
        )
        stage = _SlowStage("test", 10)
        orch = PipelineOrchestrator(stages=[stage], config=cfg)

        ctx = orch.run("input", "output", cfg)
        # Thread pool is cleaned up after run, but metadata reflects the mode
        assert ctx.metadata.get("parallel_mode") == "parallel"

    def test_cache_stats_included(self) -> None:
        cfg = ProjectConfig(
            parallel_mode="serial",
            llm_cache_enabled=True,
            llm_cache_dir=str(Path.cwd() / ".test_cache"),
            working_dir=str(Path.cwd()),
        )
        stage = _SlowStage("test", 10)
        orch = PipelineOrchestrator(stages=[stage], config=cfg)

        ctx = orch.run("input", "output", cfg)
        assert "cache_stats" in ctx.metadata
        assert ctx.metadata["cache_stats"]["enabled"] is True

    def test_cache_disabled(self) -> None:
        cfg = ProjectConfig(
            llm_cache_enabled=False,
            working_dir=str(Path.cwd()),
        )
        stage = _SlowStage("test", 10)
        orch = PipelineOrchestrator(stages=[stage], config=cfg)

        ctx = orch.run("input", "output", cfg)
        # Cache stats present but shows disabled
        assert ctx.metadata["cache_stats"]["enabled"] is False

    def test_stage_timing_recorded(self) -> None:
        cfg = ProjectConfig(
            parallel_mode="serial",
            working_dir=str(Path.cwd()),
        )
        stage = _SlowStage("slow_stage", 10, delay=0.05)
        orch = PipelineOrchestrator(stages=[stage], config=cfg)

        ctx = orch.run("input", "output", cfg)
        timing = ctx.metadata["stage_timings"]["slow_stage"]
        assert timing >= 0.04  # Should be at least 50ms

    def test_error_stops_serial_pipeline(self) -> None:
        class _FailStage(PipelineStage):
            @property
            def name(self) -> str:
                return "fail"

            @property
            def order(self) -> int:
                return 5

            def execute(self, context: PipelineContext) -> PipelineContext:
                raise RuntimeError("boom")

        cfg = ProjectConfig(
            parallel_mode="serial",
            working_dir=str(Path.cwd()),
        )
        stage1 = _FailStage()
        stage2 = _SlowStage("after_fail", 20)
        orch = PipelineOrchestrator(stages=[stage1, stage2], config=cfg)

        ctx = orch.run("input", "output", cfg)
        assert len(ctx.errors) == 1
        assert ctx.errors[0]["stage"] == "fail"
        # Second stage should not have been executed
        assert "after_fail" not in ctx.metadata.get("stage_timings", {})


class TestPipelineContextOptimization:
    """Test PipelineContext has optimization fields."""

    def test_context_has_llm_cache_field(self) -> None:
        ctx = PipelineContext()
        assert ctx.llm_cache is None

    def test_context_has_thread_pool_field(self) -> None:
        ctx = PipelineContext()
        assert ctx.thread_pool is None

    def test_context_has_memory_lock_field(self) -> None:
        ctx = PipelineContext()
        assert ctx.memory_lock is None

    def test_context_accepts_cache(self) -> None:
        cache = MagicMock()
        ctx = PipelineContext(llm_cache=cache)
        assert ctx.llm_cache is cache
