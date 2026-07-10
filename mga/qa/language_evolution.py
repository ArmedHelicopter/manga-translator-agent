"""Language evolution proofreader: checks character language changes over time."""

from __future__ import annotations

from typing import Any, Dict, List

from mga.models import Page, TranslationCandidate

from .base import QAFeedback, QAFeedbackType, QAProofreader

LANGUAGE_EVOLUTION_PROMPT = (
    "You are checking language evolution consistency.\n"
    "Character: {speaker}\n"
    "Source: {source_text}\n"
    "Translation: {translated_text}\n"
    "Chapter: {chapter_number}\n"
    "Return JSON: {{issues: [{{category, message, confidence, suggested_text}}]}}"
)


class LanguageEvolutionProofreader(QAProofreader):
    """Checks if character language has evolved per voice_evolution entries."""

    @property
    def name(self) -> str:
        return "language_evolution"

    @property
    def priority(self) -> int:
        return 50

    def proofread(
        self, page: Page, translations: List[TranslationCandidate],
        context: Dict[str, Any],
    ) -> List[QAFeedback]:
        voice_evolutions = context.get("voice_evolutions", {})
        chapter = context.get("chapter_number", 0)
        feedbacks: List[QAFeedback] = []
        for candidate in translations:
            bubble = self._get_bubble(page, candidate.bubble_id)
            if bubble is None:
                continue
            speaker = bubble.speaker_id or bubble.speaker_name
            if not speaker or speaker not in voice_evolutions:
                continue
            entries = voice_evolutions[speaker]
            feedbacks.extend(self._check_retired(bubble, candidate, entries, chapter))
            feedbacks.extend(self._check_new_patterns(bubble, candidate, entries, chapter))
        return feedbacks

    def _check_retired(
        self, bubble: Any, candidate: TranslationCandidate,
        entries: List[Dict[str, Any]], chapter: int,
    ) -> List[QAFeedback]:
        feedbacks = []
        for entry in entries:
            retire_at = entry.get("retire_at_chapter", 0)
            if retire_at <= 0 or chapter < retire_at:
                continue
            for pattern in entry.get("old_patterns", []):
                if pattern.lower() in candidate.text.lower():
                    feedbacks.append(QAFeedback(
                        bubble_id=candidate.bubble_id,
                        feedback_type=QAFeedbackType.WARNING,
                        category="evolution.retired_pattern",
                        message=f"Pattern '{pattern}' retired at ch.{retire_at} but still appears for {bubble.speaker_name}",
                        confidence=0.8,
                        original_text=bubble.source_text,
                        suggested_text=entry.get("new_pattern", "") or candidate.text,
                        rationale="Character language should evolve per voice changelog",
                    ))
        return feedbacks

    def _check_new_patterns(
        self, bubble: Any, candidate: TranslationCandidate,
        entries: List[Dict[str, Any]], chapter: int,
    ) -> List[QAFeedback]:
        feedbacks = []
        for entry in entries:
            adopt_at = entry.get("adopt_at_chapter", 0)
            if adopt_at <= 0 or chapter < adopt_at:
                continue
            new_pattern = entry.get("new_pattern", "")
            old_patterns = entry.get("old_patterns", [])
            has_old = any(p.lower() in bubble.source_text.lower() for p in old_patterns)
            has_new = new_pattern.lower() in candidate.text.lower()
            if has_old and not has_new and new_pattern:
                feedbacks.append(QAFeedback(
                    bubble_id=candidate.bubble_id,
                    feedback_type=QAFeedbackType.SUGGESTION,
                    category="evolution.missing_new_pattern",
                    message=f"Source uses pre-evolution form; consider '{new_pattern}' (adopted ch.{adopt_at})",
                    confidence=0.6,
                    original_text=bubble.source_text,
                    suggested_text=new_pattern,
                    rationale="New speech pattern should be applied post-evolution",
                ))
        return feedbacks
