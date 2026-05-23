"""Stage 5 -- QA proofreading of translations."""

from __future__ import annotations

from mga.models import ProjectConfig, TranslationCandidate
from mga.providers import get_provider
from mga.qa import QAOrchestrator
from mga.qa.base import QAFeedbackType

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

            error_bubbles = {
                bid: fbs for bid, fbs in grouped.items()
                if any(f.feedback_type == QAFeedbackType.ERROR for f in fbs)
            }
            if error_bubbles:
                self._attempt_retranslate(context, page, error_bubbles)

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
        error_bubbles: dict[str, list],
    ) -> None:
        cfg: ProjectConfig = context.project_config
        route = cfg.provider_routes.get("translation")
        if route and route.primary.provider:
            provider = get_provider(route.primary.provider, model=route.primary.model)
        else:
            provider = get_provider("openai")

        translation_by_id = {t.bubble_id: t for t in context.translations}

        for bubble_id, feedbacks in error_bubbles.items():
            candidate = translation_by_id.get(bubble_id)
            if candidate is None:
                continue

            feedback_summary = "; ".join(f.message for f in feedbacks)
            retranslate_prompt = (
                f"Re-translate the following manga dialogue. "
                f"Previous translation had issues: {feedback_summary}\n"
                f"Source: {candidate.text}\n"
                f"Return corrected Simplified Chinese translation."
            )
            try:
                raw = provider.chat([{"role": "user", "content": retranslate_prompt}])
                if raw and raw.strip():
                    candidate.text = raw.strip()
                    candidate.rationale = f"QA re-translated: {feedback_summary}"
            except Exception:
                pass
