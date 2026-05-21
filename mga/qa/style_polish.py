"""Style polish proofreader: naturalness, flow, readability, punctuation."""

from __future__ import annotations

import re
from typing import Any, Dict, List

from mga.models import Page, TranslationCandidate

from .base import QAFeedback, QAFeedbackType, QAProofreader

STYLE_PROMPT = (
    "You are a manga translation style editor.\n"
    "Target language: {target_lang}\n"
    "Source: {source_text}\n"
    "Translation: {translated_text}\n"
    "Return JSON: {{issues: [{{category, message, confidence, suggested_text}}]}}"
)

_DOUBLE_SPACE = re.compile(r"  +")
_TRAILING_PUNCT = re.compile(r"[,;]\s*$")
_CJK_LANGS = frozenset(("zh-CN", "zh-TW", "ja", "ko"))


class StylePolishProofreader(QAProofreader):
    """General style checks: naturalness, flow, readability."""

    @property
    def name(self) -> str:
        return "style_polish"

    @property
    def priority(self) -> int:
        return 60

    def proofread(
        self, page: Page, translations: List[TranslationCandidate],
        context: Dict[str, Any],
    ) -> List[QAFeedback]:
        target_lang = context.get("target_lang", "en")
        feedbacks: List[QAFeedback] = []
        for candidate in translations:
            bubble = self._get_bubble(page, candidate.bubble_id)
            if bubble is None:
                continue
            feedbacks.extend(self._check_punctuation(candidate, target_lang))
            feedbacks.extend(self._check_formatting(candidate))
            feedbacks.extend(self._check_overflow(bubble, candidate))
        return feedbacks

    def _check_punctuation(
        self, candidate: TranslationCandidate, target_lang: str,
    ) -> List[QAFeedback]:
        feedbacks = []
        text = candidate.text
        if target_lang in _CJK_LANGS and re.search(r"[a-zA-Z][,][a-zA-Z]", text):
            feedbacks.append(QAFeedback(
                bubble_id=candidate.bubble_id, feedback_type=QAFeedbackType.SUGGESTION,
                category="style.punctuation_western",
                message="Western comma in CJK text -- consider fullwidth alternative",
                confidence=0.5, original_text="", suggested_text=text,
                rationale="Target language punctuation conventions",
            ))
        if (text.count('"') + text.count("'")) % 2 != 0:
            feedbacks.append(QAFeedback(
                bubble_id=candidate.bubble_id, feedback_type=QAFeedbackType.WARNING,
                category="style.unpaired_quote",
                message="Unpaired quotation mark detected",
                confidence=0.7, original_text="", suggested_text=text,
                rationale="Balanced quotation marks required",
            ))
        return feedbacks

    def _check_formatting(self, candidate: TranslationCandidate) -> List[QAFeedback]:
        feedbacks = []
        text = candidate.text
        if _DOUBLE_SPACE.search(text):
            feedbacks.append(QAFeedback(
                bubble_id=candidate.bubble_id,
                feedback_type=QAFeedbackType.SUGGESTION,
                category="style.double_space",
                message="Double space detected in translation",
                confidence=0.9,
                original_text="", suggested_text=_DOUBLE_SPACE.sub(" ", text),
                rationale="Consistent single spacing",
            ))
        if _TRAILING_PUNCT.search(text):
            feedbacks.append(QAFeedback(
                bubble_id=candidate.bubble_id,
                feedback_type=QAFeedbackType.SUGGESTION,
                category="style.trailing_punctuation",
                message="Trailing comma or semicolon at end of bubble text",
                confidence=0.85,
                original_text="", suggested_text=text.rstrip(",; "),
                rationale="Bubbles should not end with trailing punctuation",
            ))
        return feedbacks

    def _check_overflow(
        self, bubble: Any, candidate: TranslationCandidate,
    ) -> List[QAFeedback]:
        bbox = bubble.bbox
        if bbox.width <= 0 or bbox.height <= 0:
            return []
        area = bbox.width * bbox.height
        density = len(candidate.text) / max(area, 1.0) * 10000
        if density > 8.0:
            return [QAFeedback(
                bubble_id=candidate.bubble_id,
                feedback_type=QAFeedbackType.SUGGESTION,
                category="style.overflow_risk",
                message="Text may overflow bubble -- high character density detected",
                confidence=0.6,
                original_text=bubble.source_text,
                suggested_text=candidate.text,
                rationale="Translation text density may not fit in the bubble",
            )]
        return []
