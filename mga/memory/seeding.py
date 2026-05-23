"""Seed structured memory state from external runtime output.

Reads the normalized and raw text artifacts produced by the external
manga-image-translator runtime and populates initial CharacterState,
TermState, and SceneState entries via StateManager.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from mga.memory.entities import CharacterState, SceneState, TermState
from mga.memory.state import StateManager

_CJK_RE = re.compile(r"[一-鿿㐀-䶿]{2,4}")
_KATAKANA_RE = re.compile(r"[゠-ヿ]{3,}")
_MIXED_SCRIPT_RE = re.compile(
    r"[゠-ヿ぀-ゟA-Za-z]+[一-鿿]+|[一-鿿]+[゠-ヿ぀-ゟA-Za-z]+"
)
_STOP_WORDS = frozenset({
    "的", "了", "是", "在", "不", "有", "我", "他", "这", "个", "就",
    "也", "你", "都", "我们", "他们", "什么", "没有", "可以", "已经",
    "因为", "所以", "但是", "如果", "知道", "自己", "这里", "那里",
    "怎么", "这样", "那样", "现在", "时候", "东西", "地方", "那个",
    "这个", "出来", "起来", "上去", "下来", "过来", "过去",
})


def _read_json_file(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _detect_character_names(pages: list[dict]) -> list[tuple[str, int]]:
    """Names are CJK tokens appearing on 3+ distinct pages with freq >= 5."""
    page_token_sets: list[Counter[str]] = [
        Counter(_CJK_RE.findall(p.get("source_text_joined", "")))
        for p in pages
    ]
    global_freq: Counter[str] = Counter()
    page_presence: Counter[str] = Counter()
    for pc in page_token_sets:
        for tok, cnt in pc.items():
            page_presence[tok] += 1
            global_freq[tok] += cnt

    result = [
        (name, global_freq[name])
        for name, pg_count in page_presence.items()
        if pg_count >= 3 and global_freq[name] >= 5 and name not in _STOP_WORDS
    ]
    result.sort(key=lambda x: (-x[1], x[0]))
    return result


def _detect_coined_terms(pages: list[dict]) -> list[tuple[str, int, str]]:
    """Detect mixed-script and katakana terms appearing 2+ times."""
    term_counter: Counter[str] = Counter()
    term_contexts: dict[str, str] = {}
    for page in pages:
        src = page.get("source_text_joined", "")
        for regex in (_MIXED_SCRIPT_RE, _KATAKANA_RE):
            for m in regex.finditer(src):
                term = m.group()
                if len(term) >= 2:
                    term_counter[term] += 1
                    term_contexts.setdefault(term, src[:120])
    results = [
        (term, freq, term_contexts.get(term, ""))
        for term, freq in term_counter.items() if freq >= 2
    ]
    results.sort(key=lambda x: (-x[1], x[0]))
    return results


def seed_memory_from_external_output(project_dir: str, output_dir: str) -> dict:
    """Seed memory state from external runtime output artifacts.

    Parameters
    ----------
    project_dir: Root of the project (memory/state/ lives here).
    output_dir:  Directory containing external-baseline-text artifacts.

    Returns
    -------
    dict with summary counts of what was seeded.
    """
    proj, out = Path(project_dir), Path(output_dir)
    normalized = _read_json_file(out / "external-baseline-text-normalized.json")
    summary: dict[str, int] = {
        "pages_processed": len(normalized),
        "characters_seeded": 0,
        "terms_seeded": 0,
        "scenes_seeded": 0,
    }
    if not normalized:
        return summary

    # -- Characters -----------------------------------------------------------
    detected_names = _detect_character_names(normalized)
    for name, freq in detected_names:
        cid = name.lower().replace(" ", "_")
        existing = StateManager.get_character(proj, cid)
        if existing is None:
            state = CharacterState(
                character_id=cid, name_jp=name, name_zh=name,
                provenance={"source": "auto_seed", "frequency": freq},
            )
        else:
            existing.provenance.setdefault("auto_seed_frequency", 0)
            existing.provenance["auto_seed_frequency"] = max(
                existing.provenance["auto_seed_frequency"], freq
            )
            state = existing
        StateManager.upsert_character(proj, state)
        summary["characters_seeded"] += 1

    # -- Terms ----------------------------------------------------------------
    for term, freq, ctx in _detect_coined_terms(normalized):
        tid = term.lower().replace(" ", "_")
        existing = StateManager.get_term(proj, tid)
        if existing is None:
            state = TermState(
                term_id=tid, term_jp=term, term_zh=term,
                context=ctx, frequency=freq,
                cultural_weight="auto_detected", strategy="preserve",
            )
        else:
            existing.frequency = max(existing.frequency, freq)
            state = existing
        StateManager.upsert_term(proj, state)
        summary["terms_seeded"] += 1

    # -- Scenes ---------------------------------------------------------------
    for idx, page in enumerate(normalized, start=1):
        page_id = page.get("page_id") or f"page-{idx:04d}"
        m = re.search(r"(\d+)$", page_id)
        page_num = int(m.group(1)) if m else idx
        scene_id = f"ch1_p{page_num}"
        src_text = page.get("source_text_joined", "")
        trans_text = page.get("translated_text_joined", "")
        region_count = page.get("region_count", 0)
        narrative = (trans_text or src_text)[:200]
        char_ids = [cid for cid, _ in detected_names if cid in src_text]

        existing = StateManager.get_scene(proj, scene_id)
        if existing is None:
            state = SceneState(
                scene_id=scene_id, chapter=1, page=page_num,
                scene_description=f"Page with {region_count} text regions",
                characters=char_ids, narrative_summary=narrative,
            )
        else:
            state = existing
        StateManager.upsert_scene(proj, state)
        summary["scenes_seeded"] += 1

    return summary
