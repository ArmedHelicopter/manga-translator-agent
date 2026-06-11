"""Optimized cultural adaptation service with caching and batch processing.

Performance optimizations:
1. Term cache with O(1) lookup
2. Problem classification cache
3. Batch processing for multiple bubbles
4. Lazy loading of terminology
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ── Problem Classification ────────────────────────────────────────────────────

class ProblemType(str, Enum):
    """7 cultural problem types."""
    NONE = "none"
    LOANWORD = "loanword"
    HONORIFIC = "honorific"
    IDIOM = "idiom"
    CULTURAL = "cultural"
    WORDPLAY = "wordplay"
    FICTIONAL = "fictional"


# ── Translation Strategy ──────────────────────────────────────────────────────

class Strategy(str, Enum):
    """7 translation strategies."""
    LITERAL = "literal"
    ADAPT = "adapt"
    COINED = "coined"
    TRANSLITERATE = "transliterate"
    CONTEXTUAL = "contextual"
    PRESERVE = "preserve"
    HYBRID = "hybrid"


@dataclass
class CulturalProblem:
    """Classified cultural problem."""
    problem_type: ProblemType
    text: str
    context: str = ""
    suggested_strategy: Strategy = Strategy.LITERAL
    alternative_translations: list[str] = field(default_factory=list)
    confidence: float = 1.0


# ── Honorific Levels ─────────────────────────────────────────────────────────

class HonorificLevel(str, Enum):
    """5-level honorific system."""
    POLITE = "polite"
    FORMAL = "formal"
    CASUAL = "casual"
    INTIMATE = "intimate"
    ROUGH = "rough"


@dataclass
class HonorificContext:
    """Honorific context for translation."""
    level: HonorificLevel
    speaker_formality: str = ""
    listener_formality: str = ""
    honorific_markers: list[str] = field(default_factory=list)


# ── Term Grade ───────────────────────────────────────────────────────────────

class TermGrade(str, Enum):
    """7-level term classification."""
    G1_UNIVERSAL = "g1_universal"
    G2_CULTURAL = "g2_cultural"
    G3_CONTEXT = "g3_context"
    G4_FUNCTIONAL = "g4_functional"
    G5_ADAPTED = "g5_adapted"
    G6_COINED = "g6_coined"
    G7_INVENTED = "g7_invented"


# ── Term Cache ────────────────────────────────────────────────────────────────

class TermCache:
    """O(1) term lookup cache with LRU eviction."""

    def __init__(self, max_size: int = 500) -> None:
        self._cache: dict[str, str] = {}  # term_jp -> term_zh
        self._coined: dict[str, str] = {}  # coined term -> translation
        self._access_order: OrderedDict[str, None] = OrderedDict()
        self._max_size = max_size
        self._regex_cache: dict[str, re.Pattern] = {}

    def get(self, term_jp: str) -> str | None:
        key = term_jp.lower()
        if key in self._cache:
            self._access_order.move_to_end(key)
            return self._cache[key]
        return self._coined.get(key)

    def put(self, term_jp: str, term_zh: str, coined: bool = False) -> None:
        key = term_jp.lower()
        if len(self._cache) >= self._max_size and key not in self._cache:
            # LRU eviction
            oldest = next(iter(self._access_order))
            del self._cache[oldest]
            del self._access_order[oldest]
        if coined:
            self._coined[key] = term_zh
        else:
            self._cache[key] = term_zh
            self._access_order[key] = None
            self._access_order.move_to_end(key)

    def bulk_put(self, terms: list[tuple[str, str]]) -> None:
        for term_jp, term_zh in terms:
            self.put(term_jp, term_zh)

    def match_in_text(self, text: str) -> list[tuple[str, str]]:
        """Find all matching terms in text."""
        results = []
        for term_jp, term_zh in self._cache.items():
            if term_jp in text.lower():
                results.append((term_jp, term_zh))
        return results

    def __len__(self) -> int:
        return len(self._cache) + len(self._coined)


# ── Cultural Service ──────────────────────────────────────────────────────────

class CulturalService:
    """Optimized cultural adaptation service.

    Performance features:
    - O(1) term lookup via TermCache
    - Problem classification with caching
    - Batch processing support
    """

    def __init__(self, project_dir: str | None = None):
        self.project_dir = project_dir
        self._term_cache = TermCache(max_size=500)
        self._coined_terms: dict[str, str] = {}
        self._problem_cache: dict[str, CulturalProblem] = {}
        self._load_terms()

        # Compiled regex patterns
        self._honorific_patterns = [
            re.compile(r"さん|様|くん|君|ちゃん|先生|殿"),
            re.compile(r"[様さん君ちゃん]"),
        ]
        self._katakana_pattern = re.compile(r"[ァ-ヺー]{2,}")
        self._fictional_markers = {
            "召喚", "魔法", "スキル", "アバター", "パーティ",
            "レベル", "ステータス", "経験値",
        }

    def _load_terms(self) -> None:
        """Load terminology from project memory."""
        if not self.project_dir:
            return
        try:
            from pathlib import Path
            term_file = Path(self.project_dir) / "memory" / "state" / "terms"
            if term_file.exists():
                for f in term_file.glob("*.json"):
                    import json
                    data = json.loads(f.read_text(encoding="utf-8"))
                    term_jp = data.get("term_jp", "")
                    term_zh = data.get("term_zh", "")
                    if term_jp and term_zh:
                        self._term_cache.put(term_jp, term_zh)
        except Exception:
            pass

    # ── Problem Classification ─────────────────────────────────────────────────

    def classify_problem(
        self,
        text: str,
        context: str = "",
        box_type: str = "dialogue",
    ) -> CulturalProblem:
        """Classify cultural problem in text - with caching."""
        # Check cache
        cache_key = f"{text[:50]}:{box_type}"
        if cache_key in self._problem_cache:
            return self._problem_cache[cache_key]

        problem_type = ProblemType.NONE
        suggested_strategy = Strategy.LITERAL

        # Check for honorific patterns
        if any(p.search(text) for p in self._honorific_patterns):
            problem_type = ProblemType.HONORIFIC
            suggested_strategy = Strategy.CONTEXTUAL
        # Check for katakana loanwords
        elif self._katakana_pattern.match(text.strip()):
            problem_type = ProblemType.LOANWORD
            suggested_strategy = Strategy.ADAPT
        # Check for fictional markers
        elif any(marker in text for marker in self._fictional_markers):
            problem_type = ProblemType.FICTIONAL
            suggested_strategy = Strategy.COINED

        problem = CulturalProblem(
            problem_type=problem_type,
            text=text,
            context=context,
            suggested_strategy=suggested_strategy,
        )

        # Cache result (limit cache size)
        if len(self._problem_cache) < 100:
            self._problem_cache[cache_key] = problem

        return problem

    # ── Strategy Selection ──────────────────────────────────────────────────────

    def select_strategy(
        self,
        problem: CulturalProblem,
        target_lang: str = "zh-CN",
    ) -> Strategy:
        """Select best translation strategy based on problem type."""
        if problem.problem_type == ProblemType.NONE:
            return Strategy.LITERAL
        elif problem.problem_type == ProblemType.LOANWORD:
            return Strategy.ADAPT
        elif problem.problem_type == ProblemType.HONORIFIC:
            return Strategy.CONTEXTUAL
        elif problem.problem_type == ProblemType.CULTURAL:
            return Strategy.ADAPT
        elif problem.problem_type == ProblemType.WORDPLAY:
            return Strategy.HYBRID
        elif problem.problem_type == ProblemType.FICTIONAL:
            return Strategy.COINED
        elif problem.problem_type == ProblemType.IDIOM:
            return Strategy.ADAPT
        return problem.suggested_strategy

    # ── Translation Processing ─────────────────────────────────────────────────

    def process_translation(
        self,
        bubble_id: str,
        source_text: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Process translation with cultural adaptation."""
        translation = context.get("translation", source_text)
        target_lang = context.get("target_lang", "zh-CN")

        # Apply terminology substitutions - O(1) lookup
        translation = self._apply_terminology(translation, source_text)

        # Apply honorific compensation
        if context.get("speaker"):
            translation = self._apply_honorific(
                translation,
                context["speaker"],
                context.get("listener"),
            )

        return {
            "translation": translation,
            "applied_strategies": self._get_applied_strategies(source_text),
            "footnotes": self._extract_footnotes(translation, source_text),
        }

    def _apply_terminology(self, translation: str, source: str) -> str:
        """Apply registered terminology substitutions - optimized."""
        # Fast path: check if any terms match
        if not self._term_cache:
            return translation

        # Find all matching terms
        matches = self._term_cache.match_in_text(source)
        for term_jp, term_zh in matches:
            if term_jp in source and term_zh not in translation:
                translation = translation.replace(term_jp, term_zh)

        # Check coined terms
        for term_jp, term_zh in self._coined_terms.items():
            if term_jp in source:
                translation = translation.replace(term_jp, term_zh)

        return translation

    def _apply_honorific(
        self,
        translation: str,
        speaker: dict[str, Any],
        listener: dict | None = None,
    ) -> str:
        """Apply honorific compensation based on speaker/listener relationship."""
        formality = speaker.get("formality", "casual")

        if formality in ("polite", "formal"):
            if not any(marker in translation for marker in ["请", "您", "的"]):
                if not translation.endswith(("。", "！", "？")):
                    translation += "。"
        elif formality == "intimate":
            translation = translation.replace("您", "你")
            translation = translation.replace("请", "")

        return translation

    def _get_applied_strategies(self, text: str) -> list[str]:
        """Get list of strategies applied to text."""
        strategies = []
        if self._katakana_pattern.match(text.strip()):
            strategies.append("loanword_adapt")
        if any(p.search(text) for p in self._honorific_patterns):
            strategies.append("honorific_contextual")
        if any(marker in text for marker in self._fictional_markers):
            strategies.append("fictional_coined")
        return strategies

    def _extract_footnotes(
        self,
        translation: str,
        source: str,
    ) -> list[dict[str, str]]:
        """Extract footnotes for katakana loanwords."""
        footnotes = []
        katakana_terms = self._katakana_pattern.findall(source)

        for term in katakana_terms:
            if term in translation:
                continue
            footnotes.append({
                "original": term,
                "translation": "见正文",
                "type": "loanword",
            })

        return footnotes

    # ── Batch Processing ────────────────────────────────────────────────────────

    def process_batch(
        self,
        items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Batch process multiple translations."""
        results = []
        for item in items:
            result = self.process_translation(
                item.get("bubble_id", ""),
                item.get("source_text", ""),
                item.get("context", {}),
            )
            results.append(result)
        return results

    # ── Honorific Handling ──────────────────────────────────────────────────────

    def parse_honorific_level(self, text: str) -> HonorificContext:
        """Parse honorific level from Japanese text."""
        level = HonorificLevel.CASUAL
        markers = []

        if "様" in text or "さん" in text:
            level = HonorificLevel.POLITE
            markers = ["様", "さん"]
        elif "君" in text or "くん" in text:
            level = HonorificLevel.FORMAL
            markers = ["君", "くん"]
        elif "ちゃん" in text:
            level = HonorificLevel.INTIMATE
            markers = ["ちゃん"]
        elif "先生" in text:
            level = HonorificLevel.FORMAL
            markers = ["先生"]

        return HonorificContext(
            level=level,
            honorific_markers=markers,
        )

    def compensate_honorific(
        self,
        translation: str,
        context: HonorificContext,
        target_lang: str = "zh-CN",
    ) -> str:
        """Compensate honorific level in translation."""
        if target_lang != "zh-CN":
            return translation

        if context.level == HonorificLevel.POLITE:
            if not translation.startswith(("请", "您", "请问")):
                translation = f"请{translation}"
        elif context.level == HonorificLevel.INTIMATE:
            translation = translation.replace("您", "你")
            translation = translation.replace("请", "")

        return translation

    # ── Term Management ─────────────────────────────────────────────────────────

    def register_term(
        self,
        term_jp: str,
        term_zh: str,
        *,
        context: str = "",
        strategy: str = "",
        grade: TermGrade = TermGrade.G5_ADAPTED,
    ) -> None:
        """Register a new term for consistent translation."""
        self._term_cache.put(term_jp, term_zh)

    def lookup_term(self, term_jp: str) -> str | None:
        """Lookup registered term translation."""
        return self._term_cache.get(term_jp)

    # ── Coined Term Detection ───────────────────────────────────────────────────

    def detect_coined_term(
        self,
        text: str,
        context: str = "",
    ) -> tuple[bool, str | None]:
        """Detect if text contains a coined term."""
        patterns = [
            r"[一-鿿]{2,}化",
            r"[一-鿿]{3,}拳",
            r"[A-Za-z]+[一-鿿]+",
        ]

        for pattern in self._problem_cache:  # Reuse compiled patterns
            if match := re.search(pattern, text):
                return True, match.group()

        return False, None

    def register_coined_term(
        self,
        term: str,
        translation: str,
        proposed_by: str = "system",
    ) -> None:
        """Register a coined term for future use."""
        self._coined_terms[term] = translation
        self._term_cache.put(term, translation, coined=True)

    # ── Term Classification ─────────────────────────────────────────────────────

    def classify_term(
        self,
        term: str,
        context: str = "",
    ) -> TermGrade:
        """Classify term into grade level."""
        # Check if already registered
        if self._term_cache.get(term):
            return TermGrade.G3_CONTEXT

        # Check if universal
        universal_terms = {"OK", "好吃", "谢谢", "你好"}
        if term in universal_terms:
            return TermGrade.G1_UNIVERSAL

        # Check if cultural
        cultural_terms = {"武士", "忍者", "大名", "幕府"}
        if term in cultural_terms:
            return TermGrade.G2_CULTURAL

        # Check if fictional
        if any(marker in term for marker in self._fictional_markers):
            return TermGrade.G6_COINED

        return TermGrade.G5_ADAPTED

    # ── QA Checks ───────────────────────────────────────────────────────────────

    def check_consistency(
        self,
        translations: list[dict[str, Any]],
        character_profiles: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Check cultural consistency across translations."""
        findings = []

        for trans in translations:
            bubble_id = trans.get("bubble_id", "")
            text = trans.get("text", "")
            speaker = trans.get("speaker_id", "")

            profile = character_profiles.get(speaker, {})

            # Check term consistency
            for term_jp, term_zh in self._term_cache.match_in_text(text):
                if term_zh not in text:
                    findings.append({
                        "bubble_id": bubble_id,
                        "type": "terminology",
                        "message": f"术语 '{term_jp}' 应翻译为 '{term_zh}'",
                        "suggestion": term_zh,
                    })

            # Check honorific consistency
            if profile.get("formality") == "polite":
                if "您" not in text and "请" not in text:
                    findings.append({
                        "bubble_id": bubble_id,
                        "type": "honorific",
                        "message": "敬语角色缺少敬语标记",
                        "suggestion": "在适当位置添加 '您' 或 '请'",
                    })

        return findings

    def get_stats(self) -> dict[str, Any]:
        """Get cultural service statistics."""
        return {
            "term_cache_size": len(self._term_cache),
            "coined_terms": len(self._coined_terms),
            "problem_cache_size": len(self._problem_cache),
        }


# ── Singleton Factory ─────────────────────────────────────────────────────────

_cultural_instances: dict[str, CulturalService] = {}


def get_cultural_service(project_dir: str | None = None) -> CulturalService:
    """Get or create singleton CulturalService."""
    key = str(project_dir or "default")
    if key not in _cultural_instances:
        _cultural_instances[key] = CulturalService(project_dir)
    return _cultural_instances[key]


def reset_cultural_service(project_dir: str | None = None) -> None:
    """Reset cultural service (for testing)."""
    key = str(project_dir or "default")
    _cultural_instances.pop(key, None)