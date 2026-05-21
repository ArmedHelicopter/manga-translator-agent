"""Pipeline orchestrator -- runs all stages sequentially with error resilience."""

from __future__ import annotations

import logging
import time
from typing import Sequence

from mga.exceptions import StageExecutionError
from mga.models import ProjectConfig

from .character_stage import CharacterAttributionStage
from .format_stage import FormatStage
from .output_stage import OutputStage
from .qa_stage import QAStage
from .render_stage import RenderStage
from .stages import PipelineContext, PipelineStage
from .translation_stage import TranslationStage
from .vision_stage import VisionStage

logger = logging.getLogger(__name__)

_DEFAULT_STAGES: list[PipelineStage] = [
    FormatStage(),
    VisionStage(),
    CharacterAttributionStage(),
    TranslationStage(),
    QAStage(),
    RenderStage(),
    OutputStage(),
]


class PipelineOrchestrator:
    """Execute the 7-stage pipeline sequentially, catching per-stage errors."""

    def __init__(
        self,
        stages: Sequence[PipelineStage] | None = None,
    ) -> None:
        self._stages = sorted(
            list(stages) if stages is not None else list(_DEFAULT_STAGES),
            key=lambda s: s.order,
        )

    @property
    def stages(self) -> list[PipelineStage]:
        return list(self._stages)

    def run(
        self,
        input_path: str,
        output_path: str,
        config: ProjectConfig,
    ) -> PipelineContext:
        """Execute all stages and return the final context."""
        context = PipelineContext(project_config=config)
        context.metadata["input_path"] = input_path
        context.metadata["output_path"] = output_path
        context.metadata["stage_timings"] = {}

        for stage in self._stages:
            t0 = time.monotonic()
            try:
                context = stage.execute(context)
                elapsed = time.monotonic() - t0
                context.metadata["stage_timings"][stage.name] = round(elapsed, 3)
                logger.info("Stage '%s' completed in %.3fs", stage.name, elapsed)
            except Exception as exc:
                elapsed = time.monotonic() - t0
                context.metadata["stage_timings"][stage.name] = round(elapsed, 3)
                error_entry = {
                    "stage": stage.name,
                    "error": str(exc),
                    "type": type(exc).__name__,
                }
                context.errors.append(error_entry)
                logger.error(
                    "Stage '%s' failed: %s", stage.name, exc, exc_info=True,
                )

        context.metadata["total_duration"] = sum(
            context.metadata["stage_timings"].values()
        )
        return context
