"""Main cultural adapter -- orchestrates classification, strategy, and terminology."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .classifier import classify_problem
from .honorific import HonorificCompensator
from .strategies import TranslationStrategy, STRATEGY_DESCRIPTIONS, select_strategy
from .terminology_db import TerminologyDB

_TOKEN_RE = re.compile(r"[^\s,.　]+")


class CulturalAdapter:
    """Project-scoped cultural adaptation coordinator."""

    def __init__(self, project_dir: str | Path) -> None:
        self._project_dir = Path(project_dir)
        self.terminology_db = TerminologyDB.load(self._project_dir)
        self.honorific = HonorificCompensator()

    def analyze_page(self, page_json: dict) -> dict:
        """Classify every cultural term found in a page."""
        results: dict[str, list[dict[str, Any]]] = {}
        for bubble in page_json.get("bubbles", []):
            bid = bubble.get("bubble_id", "")
            source = bubble.get("source_text", "")
            ctx = self._build_context_string(page_json, bubble)
            classified = self._classify_bubble(source, ctx)
            if classified:
                results[bid] = classified
        return results

    def get_translation_context(self, page_json: dict) -> str:
        """Return a formatted context block for the translation prompt."""
        analysis = self.analyze_page(page_json)
        all_terms: list[str] = []
        for entries in analysis.values():
            for entry in entries:
                term = entry.get("term", "")
                if term and term not in all_terms:
                    all_terms.append(term)
        db_ctx = self.terminology_db.get_injection_context(all_terms)
        parts: list[str] = []
        if db_ctx:
            parts.append(db_ctx.rstrip())
        strat_block = self._format_strategies(analysis)
        if strat_block:
            if parts:
                parts.append("")
            parts.append(strat_block)
        if not parts:
            return ""
        parts.append("")
        return "\n".join(parts)

    def process_translation(self, bubble_id: str, source: str, context: dict) -> dict:
        """Apply cultural rules to a translation candidate."""
        target_lang = context.get("target_lang", "zh-CN")
        translation = context.get("translation", source)
        adjustments: list[str] = []

        # Terminology substitution
        for term_jp in self._extract_known_terms(source):
            ts = self.terminology_db.lookup(term_jp)
            if ts and ts.term_target and ts.confirmed:
                translation = translation.replace(term_jp, ts.term_target)
                adjustments.append(f"terminology:{term_jp}")

        # Honorific compensation
        speaker = context.get("speaker")
        listener = context.get("listener")
        if speaker and listener:
            level = self.honorific.analyze(speaker, listener, context.get("relationship", {}))
            compensated = self.honorific.compensate(translation, level, target_lang)
            if compensated != translation:
                adjustments.append(f"honorific:{level.value}")
                translation = compensated

        return {"translation": translation, "adjustments": adjustments, "notes": []}

    def _classify_bubble(self, source: str, context: str) -> list[dict[str, Any]]:
        """Classify terms inside a single bubble's source text."""
        results: list[dict[str, Any]] = []
        for token in _TOKEN_RE.findall(source):
            pts = classify_problem(token, context)
            if not pts:
                continue
            strategy = select_strategy(pts[0], "medium", context)
            results.append({
                "term": token,
                "problem_types": [p.value for p in pts],
                "strategy": strategy.value,
            })
        return results

    def _build_context_string(self, page_json: dict, bubble: dict) -> str:
        """Build a context string from page-level metadata."""
        parts: list[str] = []
        if page_json.get("scene_summary"):
            parts.append(page_json["scene_summary"])
        speaker = bubble.get("speaker_name") or bubble.get("speaker_id")
        if speaker:
            parts.append(f"speaker={speaker}")
        tone = bubble.get("tone")
        if tone:
            parts.append(f"tone={tone}")
        return " | ".join(parts)

    def _extract_known_terms(self, text: str) -> list[str]:
        """Return terms from *text* that exist in the terminology DB."""
        return [jp for jp in self.terminology_db._terms if jp in text]

    def _format_strategies(self, analysis: dict[str, list[dict]]) -> str:
        """Format strategy summaries for prompt injection."""
        lines: list[str] = ["## Strategy Notes", ""]
        seen: set[str] = set()
        for entries in analysis.values():
            for entry in entries:
                sv = entry.get("strategy", "")
                if sv and sv not in seen:
                    seen.add(sv)
                    try:
                        desc = STRATEGY_DESCRIPTIONS.get(TranslationStrategy(sv), "")
                    except ValueError:
                        desc = ""
                    lines.append(f"- **{sv}**: {desc}")
        return "" if len(lines) <= 2 else "\n".join(lines) + "\n"
