"""Pipeline stage for OCR blank-page detection and recovery."""

from __future__ import annotations

import logging

from mga.exceptions import RestartPipelineSignal
from mga.ocr.detector import BlankPageDetector
from mga.ocr.models import OCRGuardConfig
from mga.ocr.recovery import RecoveryOrchestrator

from .stages import PipelineContext, PipelineStage

logger = logging.getLogger(__name__)


class OCRGuardStage(PipelineStage):
    """Monitor OCR output for consecutive blank pages and orchestrate recovery."""

    @property
    def name(self) -> str:
        return "ocr_guard"

    @property
    def order(self) -> int:
        return 22

    def execute(self, context: PipelineContext) -> PipelineContext:
        """Check for blank pages and trigger recovery if needed."""
        config = self._resolve_config(context)
        if not config.enabled:
            context.ocr_guard_state = {
                "detector_run": False,
                "enabled": False,
                "blank_sequence": None,
                "recovery_applied": None,
                "hybrid_mode_pages": [],
                "threshold": config.consecutive_blank_threshold,
            }
            context.artifacts[self.name] = dict(context.ocr_guard_state)
            return context

        detector = BlankPageDetector(config)
        sequence = detector.check_sequence(context.pages)
        context.ocr_guard_state = {
            "detector_run": True,
            "enabled": True,
            "blank_sequence": sequence.model_dump(mode="json") if sequence else None,
            "recovery_applied": None,
            "hybrid_mode_pages": [],
            "threshold": config.consecutive_blank_threshold,
            "min_text_length": config.min_text_length,
        }

        if sequence is None:
            context.artifacts[self.name] = dict(context.ocr_guard_state)
            return context

        context.metadata["ocr_guard_checkpoint"] = {
            "blank_sequence": sequence.model_dump(mode="json"),
            "page_count": len(context.pages),
        }
        logger.warning(
            "OCR guard detected blank sequence %s-%s (%d pages)",
            sequence.start_index,
            sequence.end_index,
            sequence.blank_count,
        )

        orchestrator = RecoveryOrchestrator(config)
        decision = orchestrator.prompt_user(sequence, context)
        context, should_restart_pipeline = orchestrator.apply_strategy(decision, context)
        context.artifacts[self.name] = dict(context.ocr_guard_state)

        if should_restart_pipeline:
            raise RestartPipelineSignal(
                reason="User requested OCR model switch after blank OCR detection.",
                new_ocr_model=decision.new_ocr_model,
                context_checkpoint=context,
            )

        return context

    def _resolve_config(self, context: PipelineContext) -> OCRGuardConfig:
        config = getattr(context.project_config, "ocr_guard", None)
        if config is None:
            return OCRGuardConfig()
        if isinstance(config, dict):
            return OCRGuardConfig.model_validate(config)
        if isinstance(config, OCRGuardConfig):
            return config
        return OCRGuardConfig()
