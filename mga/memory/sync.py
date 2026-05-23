"""Bidirectional sync between structured state and wiki projections."""

from __future__ import annotations

import re
from pathlib import Path

from mga.memory.entities import (
    CharacterState,
    DecisionState,
    SceneState,
    TermState,
)
from mga.memory.state import StateManager
from mga.memory.wiki import WikiProjection


def state_to_wiki(project_dir: Path) -> None:
    """Regenerate all wiki Markdown pages from structured state."""
    index = StateManager.load(project_dir)
    WikiProjection.write_all(project_dir, index)


def wiki_to_state(project_dir: Path) -> None:
    """Parse wiki Markdown files back into structured state (best-effort).

    This is intentionally conservative: it reads the Markdown files that
    exist under memory/<section>/ and attempts to extract fields using
    simple heading/list patterns.  Files that cannot be parsed are
    silently skipped.  The index is always regenerated from the
    successfully parsed entities.
    """
    base = project_dir / "memory"
    _PARSERS: dict[str, tuple[str, callable, callable]] = {
        "characters": ("characters", _parse_character_md, StateManager.upsert_character),
        "scenes": ("scenes", _parse_scene_md, StateManager.upsert_scene),
        "terms": ("terms", _parse_term_md, StateManager.upsert_term),
        "decisions": ("decisions", _parse_decision_md, StateManager.upsert_decision),
    }
    for _section, (dirname, parser, upsert) in _PARSERS.items():
        sec_dir = base / dirname
        if sec_dir.is_dir():
            for md_file in sec_dir.glob("*.md"):
                entity = parser(md_file)
                if entity:
                    upsert(project_dir, entity)
    StateManager.save(project_dir, StateManager.load(project_dir))


# ── Markdown parsing helpers (best-effort) ────────────────────


def _extract_list_field(text: str, heading: str) -> str:
    """Return the value of the first list item under *heading*, or ''."""
    pattern = rf"## {re.escape(heading)}\n((?:- .+\n?)+)"
    m = re.search(pattern, text)
    if m:
        first_line = m.group(1).strip().split("\n")[0]
        return first_line.removeprefix("- ").strip()
    return ""


def _extract_list_items(text: str, heading: str) -> list[str]:
    """Return all list item values under *heading*."""
    pattern = rf"## {re.escape(heading)}\n((?:- .+\n?)+)"
    m = re.search(pattern, text)
    if m:
        return [
            line.removeprefix("- ").strip()
            for line in m.group(1).strip().split("\n")
            if line.strip().startswith("- ")
        ]
    return []


def _parse_character_md(path: Path) -> CharacterState | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    name_jp = _extract_list_field(text, "Basic Info")
    name_zh = _extract_list_field(text, "Basic Info")  # fallback
    # Attempt to pull name_zh from a dedicated line if present
    m_zh = re.search(r"Name \(ZH\):\s*(.+)", text)
    if m_zh:
        name_zh = m_zh.group(1).strip()
    m_jp = re.search(r"Name \(JP\):\s*(.+)", text)
    if m_jp:
        name_jp = m_jp.group(1).strip()
    m_arch = re.search(r"Archetype:\s*(.+)", text)
    archetype = m_arch.group(1).strip() if m_arch else ""

    speech_patterns: dict[str, str] = {}
    for item in _extract_list_items(text, "Speech Patterns"):
        if ":" in item:
            k, v = item.split(":", 1)
            speech_patterns[k.strip()] = v.strip()

    tone_spectrum: dict[str, str] = {}
    for item in _extract_list_items(text, "Tone Spectrum"):
        if ":" in item:
            k, v = item.split(":", 1)
            tone_spectrum[k.strip()] = v.strip()

    character_id = path.stem
    return CharacterState(
        character_id=character_id,
        name_jp=name_jp,
        name_zh=name_zh,
        archetype=archetype,
        speech_patterns=speech_patterns,
        catchphrases=_extract_list_items(text, "Catchphrases"),
        tone_spectrum=tone_spectrum,
    )


def _parse_scene_md(path: Path) -> SceneState | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    # Title line: "# Scene: ch3 p5"
    m_title = re.match(r"# Scene: ch(\d+) p(\d+)", text)
    if not m_title:
        return None
    chapter = int(m_title.group(1))
    page = int(m_title.group(2))
    mood = _extract_list_field(text, "Summary")
    narrative = ""
    m_nar = re.search(r"Narrative:\s*(.+)", text)
    if m_nar:
        narrative = m_nar.group(1).strip()
    characters = _extract_list_items(text, "Characters")
    return SceneState(
        scene_id=path.stem,
        chapter=chapter,
        page=page,
        mood=mood,
        narrative_summary=narrative,
        characters=characters,
    )


def _parse_term_md(path: Path) -> TermState | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m_jp = re.search(r"Term \(JP\):\s*(.+)", text)
    m_zh = re.search(r"Term \(ZH\):\s*(.+)", text)
    m_freq = re.search(r"Frequency:\s*(\d+)", text)
    m_ctx = re.search(r"Context\n(.+)", text)
    m_cult = re.search(r"Cultural Weight:\s*(.+)", text)
    m_strat = re.search(r"Strategy:\s*(.+)", text)
    return TermState(
        term_id=path.stem,
        term_jp=m_jp.group(1).strip() if m_jp else "",
        term_zh=m_zh.group(1).strip() if m_zh else "",
        context=m_ctx.group(1).strip() if m_ctx else "",
        cultural_weight=m_cult.group(1).strip() if m_cult else "",
        strategy=m_strat.group(1).strip() if m_strat else "",
        frequency=int(m_freq.group(1)) if m_freq else 0,
    )


def _parse_decision_md(path: Path) -> DecisionState | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m_stage = re.search(r"Stage:\s*(.+)", text)
    m_conf = re.search(r"Confidence:\s*([\d.]+)", text)
    m_ts = re.search(r"Timestamp:\s*(.+)", text)
    m_dec = re.search(r"## Decision\n(.+)", text)
    m_rat = re.search(r"## Rationale\n(.+)", text)
    return DecisionState(
        decision_id=path.stem,
        stage=m_stage.group(1).strip() if m_stage else "",
        decision=m_dec.group(1).strip() if m_dec else "",
        rationale=m_rat.group(1).strip() if m_rat else "",
        confidence=float(m_conf.group(1)) if m_conf else 0.0,
        timestamp=m_ts.group(1).strip() if m_ts else "",
    )
