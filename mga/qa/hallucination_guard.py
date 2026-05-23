"""Hallucination guard — detect invented names, wrong numbers, and term inconsistencies."""

from __future__ import annotations

import re
from typing import Any

from mga.models import Bubble, Page, TranslationCandidate
from mga.qa.base import QAFeedback, QAFeedbackType, QAProofreader


# Patterns for extracting CJK names and numbers
_CJK_NAME_RE = re.compile(r"[一-鿿]{2,4}")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_KATAKANA_RE = re.compile(r"[゠-ヿ]{2,}")


class HallucinationGuardProofreader(QAProofreader):
    """Check for hallucinated content in translations."""

    @property
    def name(self) -> str:
        return "hallucination_guard"

    @property
    def priority(self) -> int:
        return 15  # Runs before character_consistency (20)

    def proofread(
        self,
        page: Page,
        translations: list[TranslationCandidate],
        context: dict[str, Any] | None = None,
    ) -> list[QAFeedback]:
        context = context or {}
        feedbacks: list[QAFeedback] = []

        profiles = context.get("character_profiles", {})
        terminology = context.get("terminology", {})

        # Build reverse terminology map (zh → jp) for checking
        term_zh_to_jp = {}
        if isinstance(terminology, dict):
            for jp, zh in terminology.items():
                if isinstance(zh, str):
                    term_zh_to_jp[zh] = jp

        for candidate in translations:
            bubble = self._find_bubble(page, candidate.bubble_id)
            if not bubble:
                continue

            # Check name fidelity
            feedbacks.extend(self._check_names(bubble, candidate, profiles))

            # Check number fidelity
            feedbacks.extend(self._check_numbers(bubble, candidate))

            # Check term consistency
            feedbacks.extend(self._check_terms(bubble, candidate, terminology))

        return feedbacks

    def _find_bubble(self, page: Page, bubble_id: str) -> Bubble | None:
        for b in page.bubbles:
            if b.bubble_id == bubble_id:
                return b
        return None

    def _check_names(
        self,
        bubble: Bubble,
        candidate: TranslationCandidate,
        profiles: dict,
    ) -> list[QAFeedback]:
        """Check that character names in source appear in translation."""
        feedbacks = []

        # Extract CJK names from source
        source_names = set(_CJK_NAME_RE.findall(bubble.source_text))

        # Get known character names from profiles
        known_names_jp = set()
        known_names_zh = set()
        for speaker_id, profile in profiles.items():
            if isinstance(profile, dict):
                if profile.get("name_jp"):
                    known_names_jp.add(profile["name_jp"])
                if profile.get("name_zh"):
                    known_names_zh.add(profile["name_zh"])

        # Check if source names that are known characters are missing from translation
        for name in source_names:
            if name in known_names_jp:
                # This is a known character name — check if Chinese equivalent appears
                zh_name = ""
                for pid, prof in profiles.items():
                    if isinstance(prof, dict) and prof.get("name_jp") == name:
                        zh_name = prof.get("name_zh", "")
                        break

                if zh_name and zh_name not in candidate.text:
                    feedbacks.append(QAFeedback(
                        bubble_id=candidate.bubble_id,
                        feedback_type=QAFeedbackType.WARNING,
                        category="hallucination.name_missing",
                        message=f"Character name '{name}' (→{zh_name}) missing from translation",
                        confidence=0.6,
                        suggested_text=f"Consider adding '{zh_name}' to the translation",
                    ))

        # Check for names in translation not present in source or known characters
        trans_names = set(_CJK_NAME_RE.findall(candidate.text))
        for name in trans_names:
            if name not in source_names and name not in known_names_zh:
                # Check if it's a known Japanese name with this Chinese translation
                is_known = False
                for pid, prof in profiles.items():
                    if isinstance(prof, dict) and prof.get("name_zh") == name:
                        is_known = True
                        break
                if not is_known:
                    feedbacks.append(QAFeedback(
                        bubble_id=candidate.bubble_id,
                        feedback_type=QAFeedbackType.SUGGESTION,
                        category="hallucination.possible_invented_name",
                        message=f"Name '{name}' in translation not found in source or known profiles",
                        confidence=0.4,
                    ))

        return feedbacks

    def _check_numbers(
        self,
        bubble: Bubble,
        candidate: TranslationCandidate,
    ) -> list[QAFeedback]:
        """Check that numbers in source match translation."""
        feedbacks = []

        source_numbers = _NUMBER_RE.findall(bubble.source_text)
        trans_numbers = _NUMBER_RE.findall(candidate.text)

        if source_numbers and trans_numbers:
            # Compare number sets
            source_set = set(source_numbers)
            trans_set = set(trans_numbers)

            missing = source_set - trans_set
            added = trans_set - source_set

            if missing:
                feedbacks.append(QAFeedback(
                    bubble_id=candidate.bubble_id,
                    feedback_type=QAFeedbackType.WARNING,
                    category="hallucination.number_missing",
                    message=f"Numbers from source missing in translation: {', '.join(missing)}",
                    confidence=0.7,
                ))

            if added:
                feedbacks.append(QAFeedback(
                    bubble_id=candidate.bubble_id,
                    feedback_type=QAFeedbackType.WARNING,
                    category="hallucination.number_added",
                    message=f"Numbers in translation not in source: {', '.join(added)}",
                    confidence=0.6,
                ))

        elif source_numbers and not trans_numbers:
            feedbacks.append(QAFeedback(
                bubble_id=candidate.bubble_id,
                feedback_type=QAFeedbackType.WARNING,
                category="hallucination.numbers_lost",
                message="Source contains numbers but translation has none",
                confidence=0.5,
            ))

        return feedbacks

    def _check_terms(
        self,
        bubble: Bubble,
        candidate: TranslationCandidate,
        terminology: dict,
    ) -> list[QAFeedback]:
        """Check that translated terms match the terminology database."""
        feedbacks = []

        if not terminology:
            return feedbacks

        # Extract Japanese terms from source that are in the terminology DB
        for jp_term, zh_term in terminology.items():
            if not isinstance(zh_term, str):
                continue
            if jp_term in bubble.source_text and zh_term not in candidate.text:
                feedbacks.append(QAFeedback(
                    bubble_id=candidate.bubble_id,
                    feedback_type=QAFeedbackType.SUGGESTION,
                    category="hallucination.term_inconsistency",
                    message=f"Term '{jp_term}' (→'{zh_term}') from terminology DB not found in translation",
                    confidence=0.5,
                ))

        return feedbacks
