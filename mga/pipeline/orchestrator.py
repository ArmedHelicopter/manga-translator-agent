"""Pipeline orchestrator -- runs all stages sequentially with error resilience."""

from __future__ import annotations

import logging
import time
from typing import Sequence

from mga.exceptions import RestartPipelineSignal, StageExecutionError
from mga.models import ProjectConfig

from .character_stage import CharacterAttributionStage
from .format_stage import FormatStage
from .ocr_guard_stage import OCRGuardStage
from .output_stage import OutputStage
from .qa_stage import QAStage
from .render_stage import RenderStage
from .speaker_attribution_stage import SpeakerAttributionStage
from .stages import PipelineContext, PipelineStage
from .translation_stage import TranslationStage
from .vision_stage import OCRArtifactStage, VisionEnrichmentStage

logger = logging.getLogger(__name__)

_DEFAULT_STAGES: list[PipelineStage] = [
    FormatStage(),
    OCRArtifactStage(),
    OCRGuardStage(),  # Detect blank pages, prompt recovery / model switch
    VisionEnrichmentStage(),
    SpeakerAttributionStage(),
    CharacterAttributionStage(),
    TranslationStage(),
    QAStage(),
    RenderStage(),
    OutputStage(),
]

_NOVEL_STAGES: list[PipelineStage] = [
    FormatStage(),
    CharacterAttributionStage(),
    TranslationStage(),
    QAStage(),
    OutputStage(),
]


class PipelineOrchestrator:
    """Execute the 7-stage pipeline sequentially, catching per-stage errors."""

    def __init__(
        self,
        stages: Sequence[PipelineStage] | None = None,
        config: ProjectConfig | None = None,
    ) -> None:
        if stages is not None:
            self._stages = sorted(list(stages), key=lambda s: s.order)
        elif config is not None and config.pipeline_mode == "novel":
            self._stages = list(_NOVEL_STAGES)
        else:
            self._stages = list(_DEFAULT_STAGES)

    @property
    def stages(self) -> list[PipelineStage]:
        return list(self._stages)

    def run(
        self,
        input_path: str,
        output_path: str,
        config: ProjectConfig,
        metadata: dict | None = None,
    ) -> PipelineContext:
        """Execute all stages and return the final context."""
        return self._run_impl(input_path, output_path, config, metadata, restart_count=0)

    def _run_impl(
        self,
        input_path: str,
        output_path: str,
        config: ProjectConfig,
        metadata: dict | None,
        restart_count: int,
    ) -> PipelineContext:
        """Internal run with restart support (max 1 restart to avoid loops)."""
        context = PipelineContext(project_config=config)
        context.metadata["input_path"] = input_path
        context.metadata["output_path"] = output_path
        context.metadata["stage_timings"] = {}
        context.metadata["executed_stages"] = []
        context.metadata["parallel_mode"] = config.parallel_mode if config else "serial"
        context.metadata["cache_stats"] = {
            "enabled": bool(config.llm_cache_enabled) if config else False,
            "dir": config.llm_cache_dir if config else None,
        }
        if metadata:
            context.metadata.update(metadata)

        for stage in self._stages:
            t0 = time.monotonic()
            try:
                context = stage.execute(context)
                elapsed = time.monotonic() - t0
                context.metadata["stage_timings"][stage.name] = round(elapsed, 3)
                context.metadata["executed_stages"].append(stage.name)
                logger.info("Stage '%s' completed in %.3fs", stage.name, elapsed)
            except RestartPipelineSignal as sig:
                elapsed = time.monotonic() - t0
                context.metadata["stage_timings"][stage.name] = round(elapsed, 3)
                if restart_count >= 1:
                    logger.warning(
                        "RestartPipelineSignal received but already restarted once; "
                        "skipping restart to avoid loop. Stage: %s",
                        stage.name,
                    )
                    context.errors.append(
                        {
                            "stage": stage.name,
                            "error": f"RestartPipelineSignal ignored (already restarted): {sig}",
                            "type": "RestartPipelineSignal",
                        }
                    )
                    break
                logger.info(
                    "RestartPipelineSignal: %s  Restarting pipeline (attempt %d/1).",
                    sig,
                    restart_count + 1,
                )
                context.metadata["restart_signal"] = {
                    "reason": str(sig),
                    "new_ocr_model": sig.new_ocr_model,
                }
                return self._run_impl(
                    input_path, output_path, config, metadata, restart_count + 1,
                )
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
                break

        context.metadata["total_duration"] = sum(
            context.metadata["stage_timings"].values()
        )
        return context
