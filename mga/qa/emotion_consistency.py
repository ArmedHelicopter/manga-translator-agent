"""Emotion consistency proofreader: tone-to-scene mood and emotional progression."""

from __future__ import annotations

from typing import Any, Dict, List

from mga.models import Page, TranslationCandidate

from .base import QAFeedback, QAFeedbackType, QAProofreader

EMOTION_PROMPT = (
    "You are auditing emotional consistency of a manga translation.\n"
    "Scene mood: {scene_mood}\n"
    "Source: {source_text} (tone: {source_tone})\n"
    "Translation: {translated_text}\n"
    "Return JSON: {{issues: [{{category, message, confidence, suggested_text}}]}}"
)

_SCENE_MOOD_EMOTION = {
    "battle": {"forbidden": ["romantic", "comedy"]},
    "farewell": {"forbidden": ["comedy"]},
    "comedy": {"forbidden": ["horror"]},
    "horror": {"forbidden": ["comedy", "romantic"]},
    "romance": {"forbidden": ["horror", "comedy"]},
}

_OPPOSITE_EMOTIONS = {
    frozenset(("excitement", "sadness")),
    frozenset(("anger", "affection")),
}


class EmotionConsistencyProofreader(QAProofreader):
    """Checks emotional tone matches scene mood and progression."""

    @property
    def name(self) -> str:
        return "emotion_consistency"

    @property
    def priority(self) -> int:
        return 40

    def proofread(
        self, page: Page, translations: List[TranslationCandidate],
        context: Dict[str, Any],
    ) -> List[QAFeedback]:
        scene_mood = context.get("scene_mood", page.scene_summary)
        prev_emotions = context.get("previous_page_emotions", [])
        feedbacks: List[QAFeedback] = []
        for candidate in translations:
            bubble = self._get_bubble(page, candidate.bubble_id)
            if bubble is None:
                continue
            feedbacks.extend(self._check_scene_mood(bubble, candidate, scene_mood))
            feedbacks.extend(self._check_progression(bubble, candidate, prev_emotions))
        return feedbacks

    def _check_scene_mood(
        self, bubble: Any, candidate: TranslationCandidate, scene_mood: str,
    ) -> List[QAFeedback]:
        if not scene_mood:
            return []
        mood_key = scene_mood.lower().split()[0]
        mood_rules = _SCENE_MOOD_EMOTION.get(mood_key)
        if not mood_rules:
            return []
        detected = bubble.tone or self._detect_emotion_broad(candidate.text)
        if detected in mood_rules["forbidden"]:
            return [QAFeedback(
                bubble_id=candidate.bubble_id,
                feedback_type=QAFeedbackType.WARNING,
                category="emotion.scene_mismatch",
                message=f"Detected '{detected}' tone in '{scene_mood}' scene",
                confidence=0.65,
                original_text=bubble.source_text,
                suggested_text=candidate.text,
                rationale="Emotional register should match scene context",
            )]
        return []

    def _detect_emotion_broad(self, text: str) -> str:
        excl = text.count("!")
        ellipsis = text.count("...") + text.count("…")
        if excl >= 2:
            return "excitement"
        if ellipsis >= 1 and excl == 0:
            return "sadness"
        if "?" in text and excl == 0:
            return "confusion"
        return "neutral"

    def _check_progression(
        self, bubble: Any, candidate: TranslationCandidate,
        prev_emotions: List[str],
    ) -> List[QAFeedback]:
        if not prev_emotions:
            return []
        current = self._detect_emotion_broad(candidate.text)
        last = prev_emotions[-1]
        if current == last or current == "neutral" or last == "neutral":
            return []
        if frozenset((current, last)) in _OPPOSITE_EMOTIONS:
            return [QAFeedback(
                bubble_id=candidate.bubble_id,
                feedback_type=QAFeedbackType.SUGGESTION,
                category="emotion.progression_jump",
                message=f"Emotional jump from '{last}' to '{current}' may need transitional phrasing",
                confidence=0.5,
                original_text=bubble.source_text,
                suggested_text=candidate.text,
                rationale="Abrupt emotion changes between bubbles can feel unnatural",
            )]
        return []
