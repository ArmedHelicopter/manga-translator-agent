"""Stage 5 -- QA proofreading of translations."""

from __future__ import annotations

from typing import Any

from mga.models import ProjectConfig, TranslationCandidate
from mga.qa import QAOrchestrator

from .stages import PipelineContext, PipelineStage


class QAStage(PipelineStage):
    """Proofread translations and optionally re-translate flagged bubbles."""

    @property
    def name(self) -> str:
        return "qa"

    @property
    def order(self) -> int:
        return 50

    def execute(self, context: PipelineContext) -> PipelineContext:
        orchestrator = QAOrchestrator()
        all_findings: list[dict] = []
        per_page: dict[str, list[dict]] = {}

        for page in context.pages:
            page_translations = self._translations_for_page(page, context)
            if not page_translations:
                continue

            feedbacks = orchestrator.proofread(
                page, page_translations, context.memory_context,
            )
            grouped = orchestrator.group_by_bubble(feedbacks)
            page_findings = self._serialize_findings(feedbacks)
            per_page[page.page_id] = page_findings
            all_findings.extend(page_findings)

            if context.project_config.save_debug_json:
                self._attempt_retranslate(context, page, grouped)

        context.qa_report = {
            "passed": len(all_findings) == 0,
            "total_findings": len(all_findings),
            "per_page": per_page,
        }
        context.artifacts[self.name] = context.qa_report
        return context

    def _translations_for_page(
        self, page: object, context: PipelineContext,
    ) -> list[TranslationCandidate]:
        page_ids = {b.bubble_id for b in page.bubbles}
        return [t for t in context.translations if t.bubble_id in page_ids]

    def _serialize_findings(self, feedbacks: list) -> list[dict]:
        return [fb.model_dump() for fb in feedbacks]

    def _attempt_retranslate(
        self, context: PipelineContext, page: object,
        grouped: dict[str, list],  # noqa: ARG002
    ) -> None:
        """Placeholder: re-translate bubbles with error-level feedback."""
        # Full re-translation requires provider access and is deferred
        # to a future iteration per SPEC Section 5.
