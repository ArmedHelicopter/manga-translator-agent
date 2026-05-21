"""Translation strategy selection for cultural adaptation."""

from __future__ import annotations

from enum import Enum

from .classifier import CulturalProblemType


class TranslationStrategy(Enum):
    """Approaches for rendering cultural content in the target language.

    Named to match SPEC §8.2: literal, adapt, coined, transliterate,
    contextual, preserve, hybrid.  OMIT is kept as an internal fallback.
    """

    LITERAL = "literal"
    ADAPT = "adapt"
    COINED = "coined"
    TRANSLITERATE = "transliterate"
    CONTEXTUAL = "contextual"
    PRESERVE = "preserve"
    HYBRID = "hybrid"
    OMIT = "omit"

    # Legacy aliases (kept for backward compat with existing call sites)
    CALQUE = "calque"
    PRESERVE_ORIGINAL = "preserve_original"
    EXPLANATORY = "explanatory"
    EQUIVALENT = "equivalent"


# Default strategy matrix: problem_type -> (high_weight, mid_weight, low_weight)
_DEFAULT_MATRIX: dict[
    CulturalProblemType,
    tuple[TranslationStrategy, TranslationStrategy, TranslationStrategy],
] = {
    CulturalProblemType.HONORIFIC: (
        TranslationStrategy.ADAPT,
        TranslationStrategy.TRANSLITERATE,
        TranslationStrategy.LITERAL,
    ),
    CulturalProblemType.COINED_TERM: (
        TranslationStrategy.COINED,
        TranslationStrategy.PRESERVE,
        TranslationStrategy.HYBRID,
    ),
    CulturalProblemType.CULTURAL_CONCEPT: (
        TranslationStrategy.HYBRID,
        TranslationStrategy.ADAPT,
        TranslationStrategy.TRANSLITERATE,
    ),
    CulturalProblemType.ONOMATOPOEIA: (
        TranslationStrategy.ADAPT,
        TranslationStrategy.TRANSLITERATE,
        TranslationStrategy.LITERAL,
    ),
    CulturalProblemType.FICTIONAL_SCRIPT: (
        TranslationStrategy.PRESERVE,
        TranslationStrategy.COINED,
        TranslationStrategy.OMIT,
    ),
    CulturalProblemType.IDIOM: (
        TranslationStrategy.ADAPT,
        TranslationStrategy.HYBRID,
        TranslationStrategy.TRANSLITERATE,
    ),
    CulturalProblemType.FORM_OF_ADDRESS: (
        TranslationStrategy.ADAPT,
        TranslationStrategy.TRANSLITERATE,
        TranslationStrategy.LITERAL,
    ),
}

_WEIGHT_ORDER = {"high": 0, "medium": 1, "low": 2}

# Strategy descriptions for prompt injection and debugging.
STRATEGY_DESCRIPTIONS: dict[TranslationStrategy, str] = {
    TranslationStrategy.LITERAL: "Translate word-for-word, preserving Japanese structure.",
    TranslationStrategy.ADAPT: "Localise to a culturally equivalent target-language expression.",
    TranslationStrategy.COINED: "Invent a new target-language term that mirrors the source feel.",
    TranslationStrategy.TRANSLITERATE: "Render phonetically in the target language.",
    TranslationStrategy.CONTEXTUAL: "Choose the rendering based on surrounding context.",
    TranslationStrategy.PRESERVE: "Keep the original term untranslated with optional gloss.",
    TranslationStrategy.HYBRID: "Combine a translated term with an explanatory note.",
    TranslationStrategy.OMIT: "Drop the term when it adds no narrative value.",
    # Legacy aliases
    TranslationStrategy.CALQUE: "Adapt as a loan-calque, keeping the foreign flavour.",
    TranslationStrategy.PRESERVE_ORIGINAL: "Keep the original term untranslated with optional gloss.",
    TranslationStrategy.EXPLANATORY: "Use a short explanatory phrase in the target language.",
    TranslationStrategy.EQUIVALENT: "Replace with a culturally equivalent target-language expression.",
}


def select_strategy(
    problem_type: CulturalProblemType,
    cultural_weight: str,
    context: str,
) -> TranslationStrategy:
    """Select the best translation strategy for a given cultural problem.

    Args:
        problem_type: The classified cultural problem type.
        cultural_weight: Importance level -- ``"high"``, ``"medium"``, or ``"low"``.
        context: Surrounding text for additional heuristics.

    Returns:
        The recommended :class:`TranslationStrategy`.
    """
    weight_idx = _WEIGHT_ORDER.get(cultural_weight, 1)
    strategies = _DEFAULT_MATRIX.get(problem_type)
    if strategies is None:
        return TranslationStrategy.LITERAL

    base = strategies[weight_idx]

    # Context-driven overrides
    if problem_type == CulturalProblemType.HONORIFIC:
        if any(kw in context for kw in ("narration", "inner_monologue", "旁白")):
            if base == TranslationStrategy.ADAPT:
                return TranslationStrategy.TRANSLITERATE

    if problem_type == CulturalProblemType.ONOMATOPOEIA:
        if any(kw in context for kw in ("sfx", "sound_effect", "音效")):
            return TranslationStrategy.PRESERVE

    if problem_type == CulturalProblemType.FICTIONAL_SCRIPT:
        if "title" in context.lower() or "logo" in context.lower():
            return TranslationStrategy.PRESERVE

    return base


def describe_strategy(strategy: TranslationStrategy) -> str:
    """Return a human-readable description of the strategy."""
    return STRATEGY_DESCRIPTIONS.get(strategy, "No description available.")
