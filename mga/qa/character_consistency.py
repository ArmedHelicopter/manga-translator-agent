"""Character consistency proofreader: voice, catchphrases, self-reference patterns."""

from __future__ import annotations

from typing import Any, Dict, List

from mga.models import Page, TranslationCandidate

from .base import QAFeedback, QAFeedbackType, QAProofreader

CHARACTER_CONSISTENCY_PROMPT = (
    "You are auditing character voice consistency.\n"
    "Character profile: {profile}\n"
    "Source: {source_text}\n"
    "Translation: {translated_text}\n"
    "Return JSON: {{issues: [{{category, message, confidence, suggested_text}}]}}"
)


class CharacterConsistencyProofreader(QAProofreader):
    """Checks character voice consistency against profiles."""

    @property
    def name(self) -> str:
        return "character_consistency"

    @property
    def priority(self) -> int:
        return 20

    def proofread(
        self, page: Page, translations: List[TranslationCandidate],
        context: Dict[str, Any],
    ) -> List[QAFeedback]:
        profiles = context.get("character_profiles", {})
        recent = context.get("recent_translations", {})
        feedbacks: List[QAFeedback] = []
        for candidate in translations:
            bubble = self._get_bubble(page, candidate.bubble_id)
            if bubble is None:
                continue
            speaker = bubble.speaker_id or bubble.speaker_name
            if not speaker or speaker not in profiles:
                continue
            profile = profiles[speaker]
            feedbacks.extend(self._check_catchphrases(bubble, candidate, profile))
            feedbacks.extend(self._check_tone(bubble, candidate, profile))
            feedbacks.extend(self._check_voice_stability(candidate, speaker, recent))
        return feedbacks

    def _check_catchphrases(
        self, bubble: Any, candidate: TranslationCandidate, profile: Dict[str, Any],
    ) -> List[QAFeedback]:
        feedbacks = []
        for phrase in profile.get("catchphrases", []):
            src_has = phrase.lower() in bubble.source_text.lower()
            trans_has = phrase.lower() in candidate.text.lower()
            if src_has and not trans_has:
                feedbacks.append(QAFeedback(
                    bubble_id=candidate.bubble_id,
                    feedback_type=QAFeedbackType.WARNING,
                    category="character.catchphrase_missing",
                    message=f"Expected catchphrase '{phrase}' not found in translation",
                    confidence=0.7,
                    original_text=bubble.source_text,
                    suggested_text=candidate.text,
                    rationale="Character catchphrases should be preserved",
                ))
        return feedbacks

    def _check_tone(
        self, bubble: Any, candidate: TranslationCandidate, profile: Dict[str, Any],
    ) -> List[QAFeedback]:
        expected_tones = profile.get("tones", [])
        source_tone = bubble.tone
        if not source_tone or not expected_tones:
            return []
        if source_tone not in expected_tones:
            return [QAFeedback(
                bubble_id=candidate.bubble_id,
                feedback_type=QAFeedbackType.SUGGESTION,
                category="character.tone_mismatch",
                message=f"Tone '{source_tone}' is not in profile tones {expected_tones}",
                confidence=0.6,
                original_text=bubble.source_text,
                suggested_text=candidate.text,
                rationale="Bubble tone should align with character profile",
            )]
        return []

    def _check_voice_stability(
        self, candidate: TranslationCandidate, speaker: str,
        recent_translations: Dict[str, List[str]],
    ) -> List[QAFeedback]:
        recent_list = recent_translations.get(speaker, [])
        if len(recent_list) < 2:
            return []
        avg_len = sum(len(t) for t in recent_list) / len(recent_list)
        cur_len = len(candidate.text)
        if avg_len > 0 and abs(cur_len - avg_len) / avg_len > 0.8:
            return [QAFeedback(
                bubble_id=candidate.bubble_id,
                feedback_type=QAFeedbackType.SUGGESTION,
                category="character.voice_drift",
                message=f"Translation length deviates significantly from recent {speaker} lines",
                confidence=0.55,
                original_text="",
                suggested_text=candidate.text,
                rationale="Large style shift may indicate voice drift",
            )]
        return []
