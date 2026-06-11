"""Tests for parallel execution helper behavior."""

from __future__ import annotations

import time

import pytest

from mga.pipeline.parallel_executor import ParallelExecutionError, ParallelExecutor


def test_parallel_executor_preserves_order() -> None:
    """Output order follows input order even when tasks complete independently."""

    def square(value: int, _ctx: dict) -> int:
        time.sleep(0.01)
        return value * value

    with ParallelExecutor(max_workers=3) as executor:
        results = executor.map([1, 2, 3, 4, 5], square)

    assert results == [1, 4, 9, 16, 25]


def test_parallel_executor_handles_errors() -> None:
    """Worker failures are aggregated with their input indexes."""

    def fail_on_even(value: int, _ctx: dict) -> int:
        if value % 2 == 0:
            raise ValueError(f"Even: {value}")
        return value

    with ParallelExecutor(max_workers=2) as executor:
        with pytest.raises(ParallelExecutionError) as exc_info:
            executor.map([1, 2, 3, 4], fail_on_even)

    assert len(exc_info.value.errors) == 2
    assert sorted(index for index, _exc in exc_info.value.errors) == [1, 3]


def test_parallel_executor_timeout() -> None:
    """Timeouts raise the aggregate execution error."""

    def slow_func(value: int, _ctx: dict) -> int:
        time.sleep(0.2)
        return value

    with ParallelExecutor(max_workers=1, timeout=0.01) as executor:
        with pytest.raises(ParallelExecutionError):
            executor.map([1, 2], slow_func)


def test_parallel_executor_context_sharing() -> None:
    """Shared context is passed to every worker."""

    def use_context(value: int, ctx: dict) -> int:
        return value + ctx["offset"]

    with ParallelExecutor(max_workers=2) as executor:
        results = executor.map([1, 2, 3], use_context, context={"offset": 10})

    assert results == [11, 12, 13]


def test_parallel_executor_context_manager() -> None:
    """Context manager usage shuts down the underlying executor."""

    with ParallelExecutor(max_workers=2) as executor:
        results = executor.map([1, 2, 3], lambda value, _ctx: value * 2)
        assert results == [2, 4, 6]

    assert executor._executor._shutdown
