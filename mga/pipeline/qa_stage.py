"""Stage 5 -- QA proofreading of translations."""

from __future__ import annotations

from mga.models import ProjectConfig, TranslationCandidate
from mga.providers import ProviderCascade
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
        provider_calls: list[dict] = []
        provider_errors: list[dict] = []

        all_findings.extend(
            self._serialize_profile_warnings(
                context.memory_context.get("profile_warnings", []),
            ),
        )

        for page in context.pages:
            page_translations = self._translations_for_page(page, context)
            if not page_translations:
                continue

            feedbacks = orchestrator.proofread(
                page, page_translations, self._proofreader_context(context, page),
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
                calls, errors = self._attempt_retranslate(context, page, error_bubbles)
                provider_calls.extend(calls)
                provider_errors.extend(errors)

        context.qa_report = {
            "passed": len(all_findings) == 0,
            "total_findings": len(all_findings),
            "findings": all_findings,
            "per_page": per_page,
        }
        repair_plan = self._build_repair_plan(all_findings)
        if repair_plan:
            context.qa_report["repair_plan"] = repair_plan
        if provider_calls:
            context.qa_report["provider_cascade_calls"] = provider_calls
        if provider_errors:
            context.qa_report["provider_cascade_errors"] = provider_errors
        context.artifacts[self.name] = context.qa_report
        return context

    def _translations_for_page(
        self, page: object, context: PipelineContext,
    ) -> list[TranslationCandidate]:
        page_ids = {b.bubble_id for b in page.bubbles}
        return [t for t in context.translations if t.bubble_id in page_ids]

    def _proofreader_context(
        self,
        context: PipelineContext,
        page: object,
    ) -> dict:
        qa_context = dict(context.memory_context)
        page_cultural = context.cultural_context.get(page.page_id, {})
        if isinstance(page_cultural, dict) and page_cultural:
            qa_context["cultural_context"] = page_cultural
            analysis = page_cultural.get("analysis")
            if isinstance(analysis, dict):
                qa_context["cultural_analysis"] = analysis
        return qa_context

    def _serialize_findings(self, feedbacks: list) -> list[dict]:
        return [fb.model_dump() for fb in feedbacks]

    def _serialize_profile_warnings(self, warnings: object) -> list[dict]:
        if not isinstance(warnings, list):
            return []

        findings: list[dict] = []
        for warning in warnings:
            if not isinstance(warning, dict):
                continue

            try:
                confidence = float(warning.get("confidence", 1.0))
            except (TypeError, ValueError):
                confidence = 1.0

            finding = {
                "feedback_type": "warning",
                "category": str(warning.get("category", "character.profile_warning")),
                "bubble_id": str(warning.get("bubble_id", "")),
                "message": str(warning.get("message", "Profile maintenance warning")),
                "confidence": confidence,
                "original_text": "",
                "suggested_text": "",
                "rationale": "Profile maintenance warning",
            }
            for key, value in warning.items():
                if key not in finding:
                    finding[key] = value
            findings.append(finding)
        return findings

    def _build_repair_plan(self, findings: list[dict]) -> list[dict]:
        plan: list[dict] = []
        for finding in findings:
            target = self._repair_target(str(finding.get("category", "")))
            action = {
                "semantic": "repair_semantic_translation",
                "persona": "repair_persona_rendering",
                "layout": "repair_layout_fit",
            }.get(target, "human_review")
            plan.append({
                "bubble_id": finding.get("bubble_id", ""),
                "category": finding.get("category", ""),
                "feedback_type": getattr(
                    finding.get("feedback_type", ""),
                    "value",
                    finding.get("feedback_type", ""),
                ),
                "target": target,
                "action": action,
                "message": finding.get("message", ""),
                "confidence": finding.get("confidence", 1.0),
                "original_text": finding.get("original_text", ""),
                "suggested_text": finding.get("suggested_text", ""),
                "rationale": finding.get("rationale", ""),
            })
        return plan

    def _repair_target(self, category: str) -> str:
        semantic_prefixes = (
            "fact",
            "hallucination",
            "cultural",
            "term",
            "terminology",
            "fictional",
            "omission",
        )
        persona_prefixes = (
            "character",
            "hierarchy",
            "emotion",
            "evolution",
        )
        layout_prefixes = (
            "style",
            "layout",
            "overflow",
        )
        if category.startswith(semantic_prefixes):
            return "semantic"
        if category.startswith(persona_prefixes):
            return "persona"
        if category.startswith(layout_prefixes):
            return "layout"
        return "review"

    def _attempt_retranslate(
        self, context: PipelineContext, page: object,
        error_bubbles: dict[str, list],
    ) -> tuple[list[dict], list[dict]]:
        cfg: ProjectConfig = context.project_config
        provider_cascade = ProviderCascade(cfg, "qa")

        translation_by_id = {t.bubble_id: t for t in context.translations}
        bubble_by_id = {b.bubble_id: b for b in page.bubbles}

        for bubble_id, feedbacks in error_bubbles.items():
            candidate = translation_by_id.get(bubble_id)
            if candidate is None:
                continue
            bubble = bubble_by_id.get(bubble_id)
            source_text = getattr(bubble, "source_text", "") or candidate.text

            feedback_summary = "; ".join(f.message for f in feedbacks)
            retranslate_prompt = (
                f"Re-translate the following manga dialogue. "
                f"Previous translation had issues: {feedback_summary}\n"
                f"Source: {source_text}\n"
                f"Previous translation: {candidate.text}\n"
                f"Return corrected Simplified Chinese translation."
            )
            try:
                raw, _candidate = provider_cascade.call_chat(
                    [{"role": "user", "content": retranslate_prompt}],
                    operation="qa_retranslate",
                    trace_context={"bubble_id": bubble_id},
                )
                if raw and raw.strip():
                    candidate.text = raw.strip()
                    candidate.rationale = f"QA re-translated: {feedback_summary}"
            except Exception:
                pass
        return provider_cascade.calls, provider_cascade.errors
