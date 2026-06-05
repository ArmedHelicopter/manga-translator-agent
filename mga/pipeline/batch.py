"""Batch translation — process multiple chapters with resume capability."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .incremental import IncrementalTranslator
from .stages import PipelineContext

logger = logging.getLogger(__name__)


class BatchProcessor:
    """Process multiple chapters in parallel with resume support.

    Maintains a progress file to allow resuming interrupted batches.
    """

    def __init__(
        self,
        project_dir: str | Path,
        config: Any = None,
        max_workers: int = 1,
        provider_override: str | None = None,
        config_path: str | None = None,
        save_json: bool = False,
    ) -> None:
        self.project_dir = Path(project_dir)
        self.config = config
        self.max_workers = max_workers
        self.provider_override = provider_override
        self.config_path = config_path
        self.save_json = save_json
        self._progress_path = self.project_dir / "batch_progress.json"

    def process(
        self,
        chapters: list[dict[str, str]],
        resume: bool = True,
    ) -> dict[str, Any]:
        """Process a list of chapters.

        Args:
            chapters: List of dicts with keys:
                - input_path: str (path to chapter input)
                - output_path: str (path to chapter output)
                - chapter_id: str (unique identifier)
            resume: If True, skip already-completed chapters.

        Returns:
            Summary dict with results per chapter.
        """
        progress = self._load_progress() if resume else {}
        results: dict[str, Any] = {}

        pending = []
        for ch in chapters:
            cid = ch.get("chapter_id", ch.get("input_path", ""))
            if resume and progress.get(cid, {}).get("status") == "completed":
                logger.info("Skipping completed chapter: %s", cid)
                results[cid] = progress[cid]
                continue
            pending.append(ch)

        if not pending:
            logger.info("All chapters already completed")
            return results

        logger.info("Processing %d chapters (%d skipped)", len(pending), len(chapters) - len(pending))

        if self.max_workers <= 1:
            # Sequential processing
            for ch in pending:
                cid = ch.get("chapter_id", ch.get("input_path", ""))
                result = self._process_single(ch)
                results[cid] = result
                progress[cid] = result
                self._save_progress(progress)
        else:
            # Parallel processing
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self._process_single, ch): ch
                    for ch in pending
                }
                for future in as_completed(futures):
                    ch = futures[future]
                    cid = ch.get("chapter_id", ch.get("input_path", ""))
                    try:
                        result = future.result()
                        results[cid] = result
                        progress[cid] = result
                        self._save_progress(progress)
                    except Exception as e:
                        error_result = {"status": "failed", "error": str(e)}
                        results[cid] = error_result
                        progress[cid] = error_result
                        self._save_progress(progress)
                        logger.error("Chapter %s failed: %s", cid, e)

        summary = self._build_summary(results)
        self._save_progress(progress)
        return summary

    def _process_single(self, chapter: dict[str, str]) -> dict[str, Any]:
        """Translate a single chapter and return result metadata."""
        input_path = chapter.get("input_path", "")
        output_path = chapter.get("output_path", "")
        chapter_id = chapter.get("chapter_id", input_path)

        translator = IncrementalTranslator(
            self.project_dir,
            self._config_for_chapter(input_path, output_path),
        )
        context = translator.translate_chapter(input_path, output_path, chapter_id)

        return {
            "status": "completed" if not context.errors else "partial",
            "chapter_id": chapter_id,
            "translations": len(context.translations),
            "errors": len(context.errors),
            "input_path": input_path,
            "output_path": output_path,
        }

    def _config_for_chapter(self, input_path: str, output_path: str) -> Any:
        if self.config is not None:
            if hasattr(self.config, "model_copy"):
                return self.config.model_copy(
                    update={
                        "working_dir": input_path,
                        "output_dir": output_path,
                        "artifact_dir": output_path,
                    },
                    deep=True,
                )
            return self.config

        from mga.config.loader import build_project_config

        cfg, _ = build_project_config(
            input_path=input_path,
            output_path=output_path,
            provider_override=self.provider_override,
            save_json=self.save_json,
            dry_run=False,
            config_path=self.config_path,
        )
        cfg.save_artifacts = self.save_json
        return cfg

    def _load_progress(self) -> dict[str, Any]:
        """Load batch progress from disk."""
        if self._progress_path.exists():
            try:
                return json.loads(self._progress_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _update_progress(self, chapter_id: str, result: dict[str, Any]) -> None:
        """Update progress for a single chapter."""
        progress = self._load_progress()
        progress[chapter_id] = result
        self._save_progress(progress)

    def _save_progress(self, progress: dict[str, Any]) -> None:
        """Save batch progress to disk."""
        self._progress_path.parent.mkdir(parents=True, exist_ok=True)
        self._progress_path.write_text(
            json.dumps(progress, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _build_summary(self, results: dict[str, Any]) -> dict[str, Any]:
        """Build a summary of batch processing results."""
        total = len(results)
        completed = sum(1 for r in results.values() if r.get("status") == "completed")
        partial = sum(1 for r in results.values() if r.get("status") == "partial")
        failed = sum(1 for r in results.values() if r.get("status") == "failed")
        total_translations = sum(r.get("translations", 0) for r in results.values())
        total_errors = sum(r.get("errors", 0) for r in results.values())

        return {
            "total_chapters": total,
            "completed": completed,
            "partial": partial,
            "failed": failed,
            "total_translations": total_translations,
            "total_errors": total_errors,
            "results": results,
        }

    def get_pending_chapters(self, chapters: list[dict[str, str]]) -> list[dict[str, str]]:
        """Return chapters that haven't been completed yet."""
        progress = self._load_progress()
        return [
            ch for ch in chapters
            if progress.get(ch.get("chapter_id", ch.get("input_path", "")), {}).get("status") != "completed"
        ]

    def get_status(self, chapters: list[dict[str, str]]) -> dict[str, Any]:
        """Return progress status for a chapter manifest."""
        progress = self._load_progress()
        results: dict[str, Any] = {}
        for ch in chapters:
            cid = ch.get("chapter_id", ch.get("input_path", ""))
            saved = progress.get(cid, {})
            status = saved.get("status", "pending")
            results[cid] = {
                **saved,
                "status": status,
                "chapter_id": cid,
                "input_path": ch.get("input_path", ""),
                "output_path": ch.get("output_path", ""),
            }

        return {
            "total_chapters": len(chapters),
            "completed": sum(1 for r in results.values() if r.get("status") == "completed"),
            "partial": sum(1 for r in results.values() if r.get("status") == "partial"),
            "failed": sum(1 for r in results.values() if r.get("status") == "failed"),
            "pending": sum(1 for r in results.values() if r.get("status") == "pending"),
            "results": results,
        }

    def reset(self) -> None:
        """Clear all progress data."""
        if self._progress_path.exists():
            self._progress_path.unlink()
