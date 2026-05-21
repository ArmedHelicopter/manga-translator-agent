"""Fictional script detection — identify and flag non-standard text."""

from __future__ import annotations

import re
from typing import Any

from mga.models import Bubble, Page, TranslationCandidate
from mga.qa.base import QAFeedback, QAFeedbackType, QAProofreader


# Unicode ranges for fictional/symbol scripts
_SYMBOL_RANGES = re.compile(
    "["
    "☀-➿"          # Misc Symbols, Dingbats
    "⭐-⭕"          # Stars
    "〽-〿"          # CJK Symbols
    "㈀-㋿"          # Enclosed CJK
    "︰-﹏"          # CJK Compatibility Forms
    "\U0001F300-\U0001F9FF"  # Emojis and Symbols
    "]"
)


class FictionalScriptProofreader(QAProofreader):
    """Detect fictional scripts, symbols, and non-standard text in translations."""

    @property
    def name(self) -> str:
        return "fictional_script"

    @property
    def priority(self) -> int:
        return 25

    def proofread(
        self,
        page: Page,
        translations: list[TranslationCandidate],
        context: dict[str, Any] | None = None,
    ) -> list[QAFeedback]:
        context = context or {}
        feedbacks: list[QAFeedback] = []

        for candidate in translations:
            bubble = self._get_bubble(page, candidate.bubble_id)
            if not bubble:
                continue

            # Check source for fictional scripts
            source_symbols = _SYMBOL_RANGES.findall(bubble.source_text)
            trans_symbols = _SYMBOL_RANGES.findall(candidate.text)

            # Flag if source has symbols that translation doesn't preserve
            if source_symbols and not trans_symbols:
                feedbacks.append(QAFeedback(
                    bubble_id=candidate.bubble_id,
                    feedback_type=QAFeedbackType.WARNING,
                    category="fictional_script.symbols_lost",
                    message=f"Source contains {len(source_symbols)} symbol(s) not preserved in translation",
                    confidence=0.6,
                ))

            # Flag if translation introduces new symbols not in source
            new_symbols = set(trans_symbols) - set(source_symbols)
            if new_symbols:
                feedbacks.append(QAFeedback(
                    bubble_id=candidate.bubble_id,
                    feedback_type=QAFeedbackType.SUGGESTION,
                    category="fictional_script.symbols_added",
                    message=f"Translation contains symbol(s) not in source: {''.join(new_symbols)}",
                    confidence=0.4,
                ))

            # Check for mixed-script terms (potential fictional language)
            mixed = re.findall(r"[一-鿿][゠-ヿ]|[゠-ヿ][一-鿿]", bubble.source_text)
            if mixed:
                # These might be fictional language terms
                for term in mixed:
                    if term not in candidate.text:
                        feedbacks.append(QAFeedback(
                            bubble_id=candidate.bubble_id,
                            feedback_type=QAFeedbackType.SUGGESTION,
                            category="fictional_script.mixed_script_term",
                            message=f"Mixed-script term '{term}' from source not preserved",
                            confidence=0.3,
                        ))

        return feedbacks
