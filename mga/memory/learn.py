"""LearnEngine: extract character profiles, terminology, and style patterns
from existing translated pages using frequency analysis and pattern matching.

No LLM calls -- purely statistical heuristics suitable for initial
memory bootstrapping.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from mga.memory.entities import CharacterState, DecisionState, TermState
from mga.memory.state import StateManager

_CJK_NAME_RE = re.compile(r"[一-鿿]{2,4}")
_PHRASE_RE = re.compile(r"[一-鿿A-Za-z]{4,8}")
_TERMINOLOGY_RE = re.compile(
    r"[゠-ヿ]{3,}|[぀-ゟ]{3,}|[一-鿿]+[぀-ゟ]+"
)
_STOP = frozenset({
    "的", "了", "是", "在", "不", "有", "我", "他", "这", "个", "就",
    "也", "你", "都", "我们", "他们", "什么", "没有", "可以", "已经",
    "因为", "所以", "但是", "如果", "知道", "自己",
})


def _read_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else []


class LearnEngine:
    """Analyse existing translations and update memory state."""

    def __init__(self, project_dir: str) -> None:
        self.project_dir = Path(project_dir)

    def learn_from_translations(self, existing_translation_dir: str) -> dict:
        """Analyse translated pages and extract memory entries.

        Returns summary dict with counts of extracted entities.
        """
        trans_dir = Path(existing_translation_dir)
        normalized = _read_json(trans_dir / "external-baseline-text-normalized.json")
        summary: dict[str, int] = {
            "pages_analysed": len(normalized),
            "characters_learned": 0,
            "terms_learned": 0,
            "decisions_learned": 0,
        }
        if not normalized:
            return summary
        summary["characters_learned"] = self._learn_characters(normalized)
        summary["terms_learned"] = self._learn_terminology(normalized)
        summary["decisions_learned"] = self._learn_decisions(normalized)
        return summary

    def _learn_characters(self, pages: list[dict]) -> int:
        name_contexts: dict[str, list[str]] = {}
        name_page_count: Counter[str] = Counter()
        name_freq: Counter[str] = Counter()

        for page in pages:
            src = page.get("source_text_joined", "")
            trans = page.get("translated_text_joined", "")
            names_on_page: set[str] = set(_CJK_NAME_RE.findall(src))
            for name in names_on_page:
                name_freq[name] += 1
                name_page_count[name] += 1
                ctx_list = name_contexts.setdefault(name, [])
                snippet = (trans or src)[:150]
                if snippet not in ctx_list:
                    ctx_list.append(snippet)

        count = 0
        for name, pages_count in name_page_count.most_common():
            if pages_count < 2 or name in _STOP or len(name) < 2:
                continue
            cid = name.lower().replace(" ", "_")
            existing = StateManager.get_character(self.project_dir, cid)
            speech = _extract_speech_patterns(name_contexts.get(name, []))
            catchphrases = _extract_catchphrases(name_contexts.get(name, []))

            if existing is None:
                state = CharacterState(
                    character_id=cid, name_jp=name, name_zh=name,
                    speech_patterns=speech, catchphrases=catchphrases,
                    provenance={"source": "learn_engine",
                                "page_count": pages_count,
                                "total_freq": name_freq[name]},
                )
            else:
                for k, v in speech.items():
                    if k not in existing.speech_patterns:
                        existing.speech_patterns[k] = v
                for cp in catchphrases:
                    if cp not in existing.catchphrases:
                        existing.catchphrases.append(cp)
                existing.provenance["learn_engine_pages"] = pages_count
                state = existing
            StateManager.upsert_character(self.project_dir, state)
            count += 1
        return count

    def _learn_terminology(self, pages: list[dict]) -> int:
        term_counter: Counter[str] = Counter()
        term_translations: dict[str, set[str]] = {}

        for page in pages:
            src = page.get("source_text_joined", "")
            trans = page.get("translated_text_joined", "")
            for m in _TERMINOLOGY_RE.finditer(src):
                term = m.group()
                if len(term) >= 3:
                    term_counter[term] += 1
                    if trans:
                        term_translations.setdefault(term, set()).add(trans[:80])

        count = 0
        for term, freq in term_counter.most_common():
            if freq < 2:
                continue
            tid = term.lower().replace(" ", "_")
            existing = StateManager.get_term(self.project_dir, tid)
            zh_hint = next(iter(term_translations[term]), "") if term in term_translations else ""
            if existing is None:
                state = TermState(
                    term_id=tid, term_jp=term, term_zh=zh_hint,
                    frequency=freq, cultural_weight="learned", strategy="preserve",
                )
            else:
                existing.frequency = max(existing.frequency, freq)
                state = existing
            StateManager.upsert_term(self.project_dir, state)
            count += 1
        return count

    def _learn_decisions(self, pages: list[dict]) -> int:
        decisions: list[DecisionState] = []
        total_regions = sum(p.get("region_count", 0) for p in pages)
        total_pages = len(pages)
        avg_regions = total_regions / total_pages if total_pages else 0

        decisions.append(DecisionState(
            stage="learn",
            decision=f"Analysed {total_pages} pages, {total_regions} regions (avg {avg_regions:.1f}/page)",
            rationale="Initial translation profile extraction",
            confidence=min(1.0, avg_regions / 5.0),
        ))

        short_count = sum(
            1 for p in pages
            for line in p.get("translated_text_joined", "").split("\n")
            if 0 < len(line.strip()) <= 10
        )
        long_count = sum(
            1 for p in pages
            for line in p.get("translated_text_joined", "").split("\n")
            if len(line.strip()) > 40
        )
        if short_count + long_count > 0:
            ratio = short_count / (short_count + long_count)
            decisions.append(DecisionState(
                stage="learn",
                decision=f"Length profile: short={short_count}, long={long_count} (ratio={ratio:.2f})",
                rationale="Style pattern detection", confidence=0.6,
            ))

        for d in decisions:
            StateManager.upsert_decision(self.project_dir, d)
        return len(decisions)


def _extract_speech_patterns(contexts: list[str]) -> dict[str, str]:
    """Extract sentence-ending particle patterns from context fragments."""
    endings: Counter[str] = Counter()
    for ctx in contexts:
        for line in ctx.split("\n"):
            if line.strip():
                endings[line.rstrip()[-1]] += 1
    return {
        f"ending_{e}": f"appears {c} times"
        for e, c in endings.most_common(3) if c >= 2
    }


def _extract_catchphrases(contexts: list[str]) -> list[str]:
    """Extract repeated 4-8 char phrases as catchphrase candidates."""
    phrases: Counter[str] = Counter()
    for ctx in contexts:
        for t in _PHRASE_RE.findall(ctx):
            phrases[t] += 1
    return [p for p, c in phrases.most_common(5) if c >= 2]
