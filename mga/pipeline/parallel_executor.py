"""Thread-pool execution helpers for parallel pipeline phases."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
from typing import Any, Callable, TypeVar, cast

T = TypeVar("T")
R = TypeVar("R")


class ParallelExecutionError(Exception):
    """Aggregated errors raised by parallel execution."""

    def __init__(self, message: str, errors: list[tuple[int, Exception]]) -> None:
        super().__init__(message)
        self.errors = errors


class ParallelExecutor:
    """Run independent tasks in a thread pool while preserving input order."""

    def __init__(self, max_workers: int = 5, timeout: float = 60) -> None:
        self.max_workers = max_workers
        self.timeout = timeout
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._logger = logging.getLogger(__name__)
        self._shutdown = False

    def map(
        self,
        items: list[T],
        func: Callable[[T, dict[str, Any]], R],
        context: dict[str, Any] | None = None,
    ) -> list[R]:
        """Execute ``func`` for every item in parallel and return ordered results."""
        shared_context = context or {}
        futures = {
            self._executor.submit(func, item, shared_context): index
            for index, item in enumerate(items)
        }
        results: list[R | None] = [None] * len(items)
        errors: list[tuple[int, Exception]] = []

        try:
            for future in as_completed(futures, timeout=self.timeout):
                index = futures[future]
                try:
                    results[index] = future.result()
                except Exception as exc:  # noqa: BLE001 - aggregate worker failures.
                    self._logger.error("Parallel task %s failed: %s", index, exc)
                    errors.append((index, exc))
        except TimeoutError as exc:
            pending_errors: list[tuple[int, Exception]] = []
            for future, index in futures.items():
                if not future.done():
                    future.cancel()
                    pending_errors.append((index, exc))
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._shutdown = True
            self._logger.error("Parallel execution timeout after %ss", self.timeout)
            raise ParallelExecutionError(
                f"Execution timeout after {self.timeout}s",
                errors=[*errors, *pending_errors],
            ) from exc

        if errors:
            raise ParallelExecutionError(
                f"{len(errors)} tasks failed out of {len(items)}",
                errors=errors,
            )

        return cast(list[R], results)

    def __enter__(self) -> "ParallelExecutor":
        """Return this executor for context-manager use."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Shut down the underlying thread pool."""
        if not self._shutdown:
            self._executor.shutdown(wait=True)
            self._shutdown = True
        return False
