"""Unified Cultural Service — single entry point for cultural adaptation.

This module provides:
- Problem classification (7 types)
- Strategy selection (7 strategies)
- Terminology handling
- Honorific compensation
- Coinage detection

Usage:
    from mga.core.cultural_service import CulturalService

    service = CulturalService(project_dir)
    adapted = service.adapt_text("こんにちは", target_lang="zh-CN")
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


# === Cultural Problem Types ===

class ProblemType:
    """Cultural problem type constants."""

    HONORIFIC = "honorific"
    CULTURAL_REFERENCE = "cultural_reference"
    WORDPLAY = "wordplay"
    COINAGE = "coinage"
    IDIOM = "idiom"
    EMOTION_EXPRESSION = "emotion_expression"
    SOCIAL_NORM = "social_norm"


# === Translation Strategies ===

class Strategy:
    """Translation strategy constants."""

    LITERAL = "literal"  # Word-for-word when possible
    ADAPT = "adapt"  # Adapt to target culture
    COINED = "coined"  # Preserve coined term
    TRANSLITERATE = "transliterate"  # Keep original sound
    CONTEXTUAL = "contextual"  # Use context-dependent translation
    PRESERVE = "preserve"  # Keep original with footnote
    HYBRID = "hybrid"  # Mix of strategies


# === Term Grades ===

class TermGrade:
    """Terminology grading constants."""

    G1_UNIVERSAL = "G1"  # Universal concepts
    G2_CULTURAL_CLOSE = "G2"  # Close cultural equivalents
    G3_CULTURAL_DIFFERENT = "G3"  # Different cultural concepts
    G4_SPECIFIC = "G4"  # Culture-specific terms
    G5_INSTITUTIONAL = "G5"  # Institutions, organizations
    G6_TECHNICAL = "G6"  # Technical terms
    G7_FICTIONAL = "G7"  # Fictional world-building


# === Problem Classifier ===

class ProblemClassifier:
    """Classify cultural problems in translation."""

    # Patterns for problem detection
    HONORIFIC_PATTERNS = [
        r"さん|様|君|殿|氏|先生|先輩|後輩",
        r"敬語|尊敬語|謙譲語|丁寧語",
    ]
    CULTURAL_PATTERNS = [
        r"お盆|正月|七夕|月見|花見",
        r"神社|寺|教會",
        r"和食|洋食|中華",
    ]
    COINAGE_PATTERNS = [
        r"[぀-ゟ]+[゠-ヿ]+",  # Katakana compounds
        r"[A-Za-z]+[゠-ヿ]+",  # Romaji + katakana
    ]

    @classmethod
    def classify(cls, text: str) -> list[str]:
        """Classify problems in text. Returns list of problem types."""
        problems = []

        for pattern in cls.HONORIFIC_PATTERNS:
            if re.search(pattern, text):
                problems.append(ProblemType.HONORIFIC)
                break

        for pattern in cls.CULTURAL_PATTERNS:
            if re.search(pattern, text):
                problems.append(ProblemType.CULTURAL_REFERENCE)
                break

        for pattern in cls.COINAGE_PATTERNS:
            if re.search(pattern, text):
                problems.append(ProblemType.COINAGE)
                break

        return problems

    @classmethod
    def detect_honorific_level(cls, text: str) -> str:
        """Detect honorific level from text."""
        if any(p in text for p in ["様", "さん", "先生"]):
            return "formal"
        elif any(p in text for p in ["君", "ちゃん", "くん"]):
            return "intimate"
        return "neutral"


# === Strategy Selector ===

class StrategySelector:
    """Select appropriate translation strategy."""

    # Problem type -> default strategy mapping
    DEFAULT_STRATEGY = {
        ProblemType.HONORIFIC: Strategy.CONTEXTUAL,
        ProblemType.CULTURAL_REFERENCE: Strategy.ADAPT,
        ProblemType.WORDPLAY: Strategy.PRESERVE,
        ProblemType.COINAGE: Strategy.COINED,
        ProblemType.IDIOM: Strategy.ADAPT,
        ProblemType.EMOTION_EXPRESSION: Strategy.CONTEXTUAL,
        ProblemType.SOCIAL_NORM: Strategy.ADAPT,
    }

    @classmethod
    def select(
        cls,
        problem_types: list[str],
        term_grade: str = "",
    ) -> str:
        """Select the best strategy for given problems."""
        if not problem_types:
            return Strategy.LITERAL

        # Use highest-priority strategy
        for prob_type in [
            ProblemType.COINAGE,
            ProblemType.HONORIFIC,
            ProblemType.CULTURAL_REFERENCE,
            ProblemType.WORDPLAY,
            ProblemType.IDIOM,
            ProblemType.EMOTION_EXPRESSION,
            ProblemType.SOCIAL_NORM,
        ]:
            if prob_type in problem_types:
                return cls.DEFAULT_STRATEGY.get(prob_type, Strategy.LITERAL)

        return Strategy.LITERAL

    @classmethod
    def apply_strategy(
        cls,
        text: str,
        strategy: str,
        context: dict | None = None,
    ) -> str:
        """Apply a strategy to translate text."""
        context = context or {}

        if strategy == Strategy.LITERAL:
            return text
        elif strategy == Strategy.PRESERVE:
            return f"[{text}]"
        elif strategy == Strategy.COINED:
            return f"『{text}』"
        else:
            return text  # Default: return as-is


# === Terminology Manager ===

class TerminologyManager:
    """Manage terminology database."""

    def __init__(self, project_dir: str | None = None):
        self.project_dir = project_dir
        self._terms: dict[str, dict] = {}
        if project_dir:
            self._load_terms()

    def _load_terms(self):
        """Load terms from project directory."""
        import json
        from pathlib import Path

        term_dir = Path(self.project_dir) / "memory" / "state" / "terms"
        if not term_dir.exists():
            return

        for term_file in term_dir.glob("*.json"):
            try:
                term = json.loads(term_file.read_text(encoding="utf-8"))
                self._terms[term["term_id"]] = term
            except Exception:
                continue

    def lookup(self, term_jp: str) -> dict | None:
        """Look up a term by Japanese text."""
        for term in self._terms.values():
            if term.get("term_jp") == term_jp:
                return term
        return None

    def add_term(
        self,
        term_id: str,
        term_jp: str,
        term_zh: str,
        strategy: str = Strategy.LITERAL,
        context: str = "",
    ) -> None:
        """Add or update a term."""
        self._terms[term_id] = {
            "term_id": term_id,
            "term_jp": term_jp,
            "term_zh": term_zh,
            "strategy": strategy,
            "context": context,
            "frequency": 0,
        }

    def save(self) -> None:
        """Save terms to project directory."""
        import json
        from pathlib import Path

        if not self.project_dir:
            return

        term_dir = Path(self.project_dir) / "memory" / "state" / "terms"
        term_dir.mkdir(parents=True, exist_ok=True)

        for term_id, term in self._terms.items():
            path = term_dir / f"{term_id}.json"
            path.write_text(json.dumps(term, ensure_ascii=False, indent=2), encoding="utf-8")


# === Cultural Service ===

class CulturalService:
    """Unified cultural adaptation service."""

    def __init__(self, project_dir: str | None = None):
        self.project_dir = project_dir
        self.classifier = ProblemClassifier()
        self.selector = StrategySelector()
        self.terminology = TerminologyManager(project_dir)
        self._cache: dict[str, str] = {}

    def analyze(self, text: str) -> dict:
        """Analyze text for cultural problems."""
        problems = self.classifier.classify(text)
        strategy = self.selector.select(problems)
        term = self.terminology.lookup(text)

        return {
            "text": text,
            "problems": problems,
            "strategy": strategy,
            "term": term,
            "honorific_level": self.classifier.detect_honorific_level(text),
        }

    def adapt_text(
        self,
        text: str,
        target_lang: str = "zh-CN",
        speaker_profile: dict | None = None,
    ) -> tuple[str, list[dict]]:
        """Adapt text with cultural considerations.

        Returns:
            (adapted_text, footnotes)
        """
        # Check cache
        if text in self._cache:
            return self._cache[text], []

        # Analyze
        analysis = self.analyze(text)

        # Apply terminology
        if analysis["term"]:
            term = analysis["term"]
            if term["strategy"] == Strategy.PRESERVE:
                result = term["term_zh"]
                footnotes = [{"term": term["term_jp"], "note": term.get("context", "")}]
            else:
                result = term["term_zh"]
                footnotes = []
        else:
            # Apply strategy
            result = self.selector.apply_strategy(
                text,
                analysis["strategy"],
                speaker_profile,
            )
            footnotes = []

        self._cache[text] = result
        return result, footnotes

    def adapt_dialogue(
        self,
        text: str,
        speaker_profile: dict,
        listener_profile: dict | None = None,
        target_lang: str = "zh-CN",
    ) -> tuple[str, list[dict]]:
        """Adapt dialogue with honorific considerations.

        Returns:
            (adapted_text, footnotes)
        """
        # Honorific adaptation
        honorific_level = self.classifier.detect_honorific_level(text)

        # Adapt based on relationship
        if listener_profile and speaker_profile:
            # Check formality from profiles
            pass  # Placeholder for relationship logic

        return self.adapt_text(text, target_lang, speaker_profile)


# === Convenience Functions ===

def create_cultural_service(project_dir: str | None = None) -> CulturalService:
    """Factory function to create a CulturalService."""
    return CulturalService(project_dir)


def classify_text(text: str) -> list[str]:
    """Quick classification of text problems."""
    return ProblemClassifier.classify(text)


def select_strategy(problem_types: list[str]) -> str:
    """Quick strategy selection."""
    return StrategySelector.select(problem_types)


__all__ = [
    "ProblemType",
    "Strategy",
    "TermGrade",
    "ProblemClassifier",
    "StrategySelector",
    "TerminologyManager",
    "CulturalService",
    "create_cultural_service",
    "classify_text",
    "select_strategy",
]