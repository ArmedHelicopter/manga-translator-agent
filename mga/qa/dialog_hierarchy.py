"""Dialog hierarchy proofreader: honorific levels, form-of-address consistency."""

from __future__ import annotations

from typing import Any, Dict, List

from mga.models import Page, TranslationCandidate

from .base import QAFeedback, QAFeedbackType, QAProofreader

HIERARCHY_PROMPT = (
    "You are auditing dialog hierarchy and social register.\n"
    "Speaker: {speaker}, Listener: {listener}\n"
    "Source: {source_text}\n"
    "Translation: {translated_text}\n"
    "Return JSON: {{issues: [{{category, message, confidence, suggested_text}}]}}"
)

_DEFAULT_HIERARCHY: Dict[tuple[str, str], str] = {
    ("subordinate", "superior"): "formal", ("student", "teacher"): "formal",
    ("child", "parent"): "formal", ("junior", "senior"): "formal",
    ("superior", "subordinate"): "casual", ("teacher", "student"): "casual",
    ("parent", "child"): "casual", ("senior", "junior"): "casual",
}


class DialogHierarchyProofreader(QAProofreader):
    """Checks honorific levels and form-of-address consistency."""

    @property
    def name(self) -> str:
        return "dialog_hierarchy"

    @property
    def priority(self) -> int:
        return 30

    def proofread(
        self,
        page: Page,
        translations: List[TranslationCandidate],
        context: Dict[str, Any],
    ) -> List[QAFeedback]:
        graph = context.get("character_graph", {})
        address_rules = context.get("address_rules", {})
        feedbacks: List[QAFeedback] = []
        for candidate in translations:
            bubble = self._get_bubble(page, candidate.bubble_id)
            if bubble is None:
                continue
            speaker = bubble.speaker_id or bubble.speaker_name or ""
            listener = self._resolve_listener(bubble, context)
            feedbacks.extend(self._check_register(bubble, candidate, speaker, listener, graph))
            feedbacks.extend(self._check_address(bubble, candidate, speaker, address_rules))
        return feedbacks

    def _resolve_listener(self, bubble: Any, context: Dict[str, Any]) -> str:
        explicit = context.get("active_listeners", {}).get(bubble.bubble_id)
        return explicit or context.get("current_interlocutor", "")

    def _check_register(
        self, bubble: Any, candidate: TranslationCandidate,
        speaker: str, listener: str, graph: Dict[str, Any],
    ) -> List[QAFeedback]:
        if not speaker or not listener:
            return []
        edge = graph.get(f"{speaker}->{listener}", {})
        expected = edge.get("register") or _DEFAULT_HIERARCHY.get(
            (edge.get("speaker_role", ""), edge.get("listener_role", ""))
        )
        if not expected:
            return []
        actual = self._infer_register(candidate.text, bubble.source_text)
        if actual and expected != actual:
            return [QAFeedback(
                bubble_id=candidate.bubble_id,
                feedback_type=QAFeedbackType.ERROR,
                category="hierarchy.register_violation",
                message=f"Register mismatch: expected '{expected}' ({speaker} -> {listener}), got '{actual}'",
                confidence=0.8,
                original_text=bubble.source_text,
                suggested_text=candidate.text,
                rationale="Hierarchical relationship demands specific register",
            )]
        return []

    def _infer_register(self, translated: str, source: str) -> str | None:
        has_excl = "!" in translated
        has_dots = "..." in translated
        if has_excl and not has_dots:
            return "casual"
        if has_dots and not has_excl:
            return "formal"
        if source.endswith(("!", "!?")):
            return "casual"
        if source.endswith(("...", "…")):
            return "formal"
        return None

    def _check_address(
        self, bubble: Any, candidate: TranslationCandidate,
        speaker: str, address_rules: Dict[str, Any],
    ) -> List[QAFeedback]:
        forbidden = address_rules.get(speaker, {}).get("forbidden", [])
        return [QAFeedback(
            bubble_id=candidate.bubble_id,
            feedback_type=QAFeedbackType.WARNING,
            category="hierarchy.address_violation",
            message=f"Address term '{term}' used by {speaker} violates established rules",
            confidence=0.75,
            original_text=bubble.source_text,
            suggested_text=candidate.text,
            rationale="Form-of-address must stay consistent across the series",
        ) for term in forbidden if term.lower() in candidate.text.lower()]
