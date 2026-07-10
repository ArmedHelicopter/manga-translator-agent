"""7-level term grading strategy for cultural adaptation."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class TermGrade(str, Enum):
    """7-level grading scale for cultural terms.

    G1-G7 from most translatable to most culturally-bound:
    """
    G1_UNIVERSAL = "G1_universal"           # Universal concepts, direct translation OK
    G2_ADAPTABLE = "G2_adaptable"           # Can be adapted to target culture
    G3_LOANWORD = "G3_loanword"             # Best kept as loanword
    G4_CALQUE = "G4_calque"                 # Translated literally (calque)
    G5_CULTURAL = "G5_cultural"             # Cultural concept, needs explanation
    G6_COINED = "G6_coined"                 # Coined/fictional term, preserve original
    G7_FICTIONAL = "G7_fictional"           # Fictional script/symbol, preserve as-is


# Mapping from CulturalProblemType to default grade
_PROBLEM_TYPE_GRADES: dict[str, TermGrade] = {
    "HONORIFIC": TermGrade.G5_CULTURAL,
    "COINED_TERM": TermGrade.G6_COINED,
    "CULTURAL_CONCEPT": TermGrade.G5_CULTURAL,
    "ONOMATOPOEIA": TermGrade.G3_LOANWORD,
    "FICTIONAL_SCRIPT": TermGrade.G7_FICTIONAL,
    "IDIOM": TermGrade.G4_CALQUE,
    "FORM_OF_ADDRESS": TermGrade.G5_CULTURAL,
}

# Grade → recommended translation strategy
_GRADE_STRATEGIES: dict[TermGrade, str] = {
    TermGrade.G1_UNIVERSAL: "equivalent",
    TermGrade.G2_ADAPTABLE: "equivalent",
    TermGrade.G3_LOANWORD: "calque",
    TermGrade.G4_CALQUE: "calque",
    TermGrade.G5_CULTURAL: "explanatory",
    TermGrade.G6_COINED: "preserve_original",
    TermGrade.G7_FICTIONAL: "preserve_original",
}

# Grade → human-readable description (Chinese)
_GRADE_DESCRIPTIONS: dict[TermGrade, str] = {
    TermGrade.G1_UNIVERSAL: "通用概念，可直接翻译",
    TermGrade.G2_ADAPTABLE: "可适配目标文化的词汇",
    TermGrade.G3_LOANWORD: "音译词，保留原音",
    TermGrade.G4_CALQUE: "直译（仿造词）",
    TermGrade.G5_CULTURAL: "文化概念，需要解释说明",
    TermGrade.G6_COINED: "造词/虚构词，保留原文",
    TermGrade.G7_FICTIONAL: "虚构文字/符号，原样保留",
}


@dataclass
class TermClassification:
    """Result of classifying a term."""
    term_jp: str
    grade: TermGrade
    strategy: str
    description: str
    confidence: float = 1.0
    notes: str = ""


def classify_term(
    term_jp: str,
    problem_types: list[str],
    context: str = "",
    cultural_weight: str = "medium",
) -> TermClassification:
    """Classify a term into a grade and recommend a strategy.

    Args:
        term_jp: The Japanese term.
        problem_types: List of CulturalProblemType values.
        context: Surrounding text for context.
        cultural_weight: "high", "medium", or "low".

    Returns:
        TermClassification with grade, strategy, and description.
    """
    # Determine grade from problem types
    grade = TermGrade.G1_UNIVERSAL
    confidence = 0.5

    for pt in problem_types:
        pt_grade = _PROBLEM_TYPE_GRADES.get(pt)
        if pt_grade:
            # Take the highest (most culturally-bound) grade
            if pt_grade.value > grade.value:
                grade = pt_grade
                confidence = 0.7

    # Adjust grade based on cultural weight
    if cultural_weight == "high":
        # High cultural weight → might need to upgrade
        if grade in (TermGrade.G2_ADAPTABLE, TermGrade.G3_LOANWORD):
            grade = TermGrade.G5_CULTURAL
            confidence = 0.8
    elif cultural_weight == "low":
        # Low cultural weight → might downgrade
        if grade in (TermGrade.G5_CULTURAL, TermGrade.G6_COINED):
            grade = TermGrade.G4_CALQUE
            confidence = 0.6

    # Context-driven overrides
    if context:
        lower_ctx = context.lower()
        if any(kw in lower_ctx for kw in ["title", "logo", "sfx", "音效"]):
            if grade in (TermGrade.G3_LOANWORD, TermGrade.G4_CALQUE):
                grade = TermGrade.G6_COINED
                confidence = 0.8
        if any(kw in lower_ctx for kw in ["narration", "inner_monologue", "旁白"]):
            if grade == TermGrade.G5_CULTURAL:
                grade = TermGrade.G4_CALQUE
                confidence = 0.7

    strategy = _GRADE_STRATEGIES.get(grade, "literal")
    description = _GRADE_DESCRIPTIONS.get(grade, "未知等级")

    return TermClassification(
        term_jp=term_jp,
        grade=grade,
        strategy=strategy,
        description=description,
        confidence=confidence,
    )


def classify_batch(
    terms: list[dict[str, Any]],
) -> list[TermClassification]:
    """Classify a batch of terms.

    Each term dict should have:
    - term_jp: str
    - problem_types: list[str] (optional)
    - context: str (optional)
    - cultural_weight: str (optional)
    """
    results: list[TermClassification] = []
    for term in terms:
        results.append(classify_term(
            term_jp=term.get("term_jp", ""),
            problem_types=term.get("problem_types", []),
            context=term.get("context", ""),
            cultural_weight=term.get("cultural_weight", "medium"),
        ))
    return results
