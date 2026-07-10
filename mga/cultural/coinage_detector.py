"""Coinage detector — lifecycle for discovered coined terms."""

from __future__ import annotations

import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .classifier import CulturalProblemType, classify_problem
from .terminology_db import TermState, TerminologyDB

logger = logging.getLogger(__name__)

# Patterns for detecting coined/fictional terms
_KATAKANA_RE = re.compile(r"[゠-ヿ]{3,}")
_MIXED_SCRIPT_RE = re.compile(r"[一-鿿][゠-ヿ]|[゠-ヿ][一-鿿]")
_SYMBOL_RE = re.compile(r"[^\w\s,.。、！？!?]")


@dataclass
class CoinageCandidate:
    """A proposed coined term awaiting confirmation."""
    term_jp: str
    count: int = 0
    contexts: list[str] = field(default_factory=list)
    problem_types: list[str] = field(default_factory=list)
    suggested_translation: str = ""
    suggested_strategy: str = "preserve"
    status: str = "proposed"  # proposed, confirmed, rejected


class CoinageDetector:
    """Detect, propose, and manage coined terms across pages."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self._candidates: dict[str, CoinageCandidate] = {}

    def detect_from_text(self, source_text: str, page_id: str = "") -> list[CoinageCandidate]:
        """Scan text for potential coined terms.

        Uses multiple heuristics:
        1. Katakana runs (3+ chars) that aren't common words
        2. Mixed-script combinations (kanji+katakana)
        3. Terms classified as COINED_TERM by the classifier
        """
        candidates: list[CoinageCandidate] = []
        tokens = re.findall(r"[^\s,.。、！？!?]+", source_text)

        for token in tokens:
            is_coinage = False
            problem_types = []

            # Check 1: Katakana runs
            if _KATAKANA_RE.fullmatch(token):
                is_coinage = True
                problem_types.append("katakana_coinage")

            # Check 2: Mixed script
            if _MIXED_SCRIPT_RE.search(token) and len(token) >= 2:
                is_coinage = True
                problem_types.append("mixed_script")

            # Check 3: Classifier detection
            if not is_coinage:
                types = classify_problem(token, source_text)
                if CulturalProblemType.COINED_TERM in types:
                    is_coinage = True
                    problem_types.append("classifier_detected")

            if not is_coinage:
                continue

            # Check if already in terminology DB
            existing = self._lookup_existing(token)
            if existing and existing.confirmed:
                continue

            # Add or update candidate
            if token in self._candidates:
                self._candidates[token].count += 1
                if page_id and page_id not in self._candidates[token].contexts:
                    self._candidates[token].contexts.append(page_id)
            else:
                candidate = CoinageCandidate(
                    term_jp=token,
                    count=1,
                    contexts=[page_id] if page_id else [],
                    problem_types=problem_types,
                )
                self._candidates[token] = candidate
                candidates.append(candidate)

        return candidates

    def detect_from_pages(self, pages: list[Any]) -> list[CoinageCandidate]:
        """Scan multiple pages for coined terms."""
        all_candidates: list[CoinageCandidate] = []
        for page in pages:
            page_id = getattr(page, "page_id", "")
            for bubble in getattr(page, "bubbles", []):
                source_text = getattr(bubble, "source_text", "")
                if source_text:
                    found = self.detect_from_text(source_text, page_id)
                    all_candidates.extend(found)
        return all_candidates

    def get_proposals(self, min_count: int = 2) -> list[CoinageCandidate]:
        """Get proposed coinages that appear at least min_count times."""
        return [
            c for c in self._candidates.values()
            if c.count >= min_count and c.status == "proposed"
        ]

    def confirm(self, term_jp: str, translation: str = "", strategy: str = "literal") -> bool:
        """Confirm a coined term and register it."""
        if term_jp not in self._candidates:
            return False

        candidate = self._candidates[term_jp]
        candidate.status = "confirmed"
        candidate.suggested_translation = translation
        candidate.suggested_strategy = strategy

        # Register in TerminologyDB
        term = TermState(
            term_jp=term_jp,
            term_target=translation,
            problem_types=candidate.problem_types,
            strategy=strategy,
            notes=f"Auto-detected coinage (count={candidate.count})",
            confirmed=True,
        )
        db = TerminologyDB.load(self.project_dir)
        db.register(term)
        db.export(self.project_dir)

        # Also register in memory state
        self._register_in_memory(term_jp, translation, strategy, candidate)

        logger.info("Confirmed coinage: %s → %s (strategy=%s)", term_jp, translation, strategy)
        return True

    def reject(self, term_jp: str) -> bool:
        """Reject a coined term proposal."""
        if term_jp not in self._candidates:
            return False
        self._candidates[term_jp].status = "rejected"
        return True

    def _lookup_existing(self, term_jp: str) -> TermState | None:
        """Check if term already exists in TerminologyDB."""
        try:
            db = TerminologyDB.load(self.project_dir)
            return db.lookup(term_jp)
        except Exception:
            return None

    def _register_in_memory(
        self,
        term_jp: str,
        term_zh: str,
        strategy: str,
        candidate: CoinageCandidate,
    ) -> None:
        """Register confirmed coinage in memory state."""
        try:
            from mga.memory.entities import TermState as MemoryTermState
            from mga.memory.state import StateManager

            term_id = term_jp.lower().replace(" ", "_")
            mem_term = MemoryTermState(
                term_id=term_id,
                term_jp=term_jp,
                term_zh=term_zh,
                context="; ".join(candidate.contexts[:5]),
                cultural_weight="coined",
                strategy=strategy,
                frequency=candidate.count,
            )
            StateManager.upsert_term(self.project_dir, mem_term)
        except Exception as e:
            logger.warning("Failed to register coinage in memory: %s", e)

    def get_all_candidates(self) -> dict[str, CoinageCandidate]:
        """Return all detected candidates."""
        return dict(self._candidates)
