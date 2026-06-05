"""Bidirectional sync between structured state and wiki projections."""

from __future__ import annotations

import json
import re
from pathlib import Path

from mga.memory.entities import (
    CharacterState,
    DecisionState,
    MemoryIndex,
    SceneState,
    TermState,
)
from mga.memory.state import StateManager
from mga.memory.wiki import (
    WikiProjection,
    normalize_work_namespace,
    work_scoped_id,
)


def state_to_wiki(project_dir: Path, work: str | None = None) -> None:
    """Regenerate all wiki Markdown pages from structured state."""
    index = StateManager.load(project_dir)
    WikiProjection.write_all(project_dir, index, work=work)


def wiki_to_state(project_dir: Path, work: str | None = None) -> None:
    """Parse wiki Markdown files back into structured state (best-effort).

    This is intentionally conservative: it reads the Markdown files that
    exist under memory/<section>/ and attempts to extract fields using
    simple heading/list patterns.  Files that cannot be parsed are
    silently skipped.  The index is always regenerated from the
    successfully parsed entities.
    """
    base = project_dir / "memory"
    work_namespace = normalize_work_namespace(work)
    _PARSERS: dict[str, tuple[str, callable, callable]] = {
        "characters": ("characters", _parse_character_md, StateManager.upsert_character),
        "scenes": ("scenes", _parse_scene_md, StateManager.upsert_scene),
        "terms": ("terms", _parse_term_md, StateManager.upsert_term),
        "decisions": ("decisions", _parse_decision_md, StateManager.upsert_decision),
    }
    for section, (dirname, parser, upsert) in _PARSERS.items():
        sec_dir = _sync_section_dir(base, dirname, work_namespace)
        if sec_dir.is_dir():
            for md_file in sec_dir.glob("*.md"):
                entity = parser(md_file)
                if entity:
                    entity = _scope_entity_for_work(section, entity, work_namespace)
                    upsert(project_dir, entity)
    index = StateManager.load(project_dir)
    index_dir = base / "indexes"
    if index_dir.is_dir():
        index_files = [index_dir / f"{work_namespace}.md"] if work_namespace else list(index_dir.glob("*.md"))
        for md_file in index_files:
            if not md_file.exists():
                continue
            parsed_index = _parse_index_md(md_file)
            if parsed_index:
                index.characters.update(parsed_index.characters)
                index.scenes.update(_scope_index_map(parsed_index.scenes, work_namespace))
                index.terms.update(_scope_index_map(parsed_index.terms, work_namespace))
                index.decisions.update(_scope_index_map(parsed_index.decisions, work_namespace))
    StateManager.save(project_dir, index)


def _sync_section_dir(base: Path, dirname: str, work_namespace: str) -> Path:
    if work_namespace and dirname in {"scenes", "terms", "decisions"}:
        return base / dirname / work_namespace
    return base / dirname


def _scope_entity_for_work(section: str, entity, work_namespace: str):
    if not work_namespace or section == "characters":
        return entity
    if section == "scenes":
        return entity.model_copy(update={"scene_id": work_scoped_id(work_namespace, entity.scene_id)})
    if section == "terms":
        return entity.model_copy(update={"term_id": work_scoped_id(work_namespace, entity.term_id)})
    if section == "decisions":
        return entity.model_copy(update={"decision_id": work_scoped_id(work_namespace, entity.decision_id)})
    return entity


def _scope_index_map(values: dict[str, str], work_namespace: str) -> dict[str, str]:
    if not work_namespace:
        return values
    return {work_scoped_id(work_namespace, key): value for key, value in values.items()}


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


def _extract_section_body(text: str, heading: str) -> str:
    """Return the body under a second-level heading."""
    pattern = rf"## {re.escape(heading)}\n(.*?)(?=\n## |\Z)"
    m = re.search(pattern, text, flags=re.S)
    return m.group(1).strip() if m else ""


def _extract_index_entries(text: str, heading: str) -> dict[str, str]:
    body = _extract_section_body(text, heading)
    entries: dict[str, str] = {}
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("- ") or line == "- _None._":
            continue
        match = re.match(r"-\s*(?P<label>.+?)\s*\(`(?P<entity_id>[^`]+)`\)\s*$", line)
        if match:
            entries[match.group("entity_id").strip()] = match.group("label").strip()
    return entries


def _parse_index_md(path: Path) -> MemoryIndex | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.lstrip().startswith("# Memory Index"):
        return None
    return MemoryIndex(
        characters=_extract_index_entries(text, "Characters"),
        scenes=_extract_index_entries(text, "Scenes"),
        terms=_extract_index_entries(text, "Terms"),
        decisions=_extract_index_entries(text, "Decisions"),
    )


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

    relationship_speech: dict[str, dict[str, object]] = {}
    for item in _extract_list_items(text, "Relationship Speech"):
        if ":" in item:
            listener, raw_rule = item.split(":", 1)
            raw_rule = raw_rule.strip()
            try:
                parsed = json.loads(raw_rule)
            except json.JSONDecodeError:
                parsed = {"note": raw_rule}
            if isinstance(parsed, dict):
                relationship_speech[listener.strip()] = parsed
            else:
                relationship_speech[listener.strip()] = {"note": str(parsed)}

    translation_notes: dict[str, str] = {}
    for item in _extract_list_items(text, "Translation Notes"):
        if ":" in item:
            k, v = item.split(":", 1)
            translation_notes[k.strip()] = v.strip()

    voice_evolutions = [
        _parse_voice_evolution_item(item)
        for item in _extract_list_items(text, "Voice Evolutions")
    ]
    voice_evolutions = [evo for evo in voice_evolutions if evo]

    provenance = _parse_key_value_section(text, "Provenance")

    character_id = path.stem
    return CharacterState(
        character_id=character_id,
        name_jp=name_jp,
        name_zh=name_zh,
        archetype=archetype,
        speech_patterns=speech_patterns,
        catchphrases=_extract_list_items(text, "Catchphrases"),
        tone_spectrum=tone_spectrum,
        relationship_speech=relationship_speech,
        translation_notes=translation_notes,
        voice_evolutions=voice_evolutions,
        provenance=provenance,
    )


def _parse_voice_evolution_item(item: str) -> dict[str, object]:
    match = re.match(r"ch(?P<chapter>\d+|\?)\s*:\s*(?P<body>.*)$", item)
    if not match:
        return {"note": item}

    raw_chapter = match.group("chapter")
    body = match.group("body").strip()
    chapter = int(raw_chapter) if raw_chapter.isdigit() else 0
    if body.startswith("{"):
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            parsed.setdefault("chapter", chapter)
            return parsed

    return {"chapter": chapter, "note": body}


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
    summary = _extract_section_body(text, "Summary")
    summary_lines = [
        line.strip()
        for line in summary.splitlines()
        if line.strip()
    ]
    description_lines = [
        line
        for line in summary_lines
        if not line.startswith("- ")
    ]
    scene_description = "\n".join(
        line for line in description_lines if line != "_No description._"
    )
    mood = ""
    m_mood = re.search(r"-\s*Mood:\s*(.+)", summary)
    if m_mood:
        mood = m_mood.group(1).strip()
    narrative = ""
    m_nar = re.search(r"-\s*Narrative:\s*(.+)", summary)
    if m_nar:
        narrative = m_nar.group(1).strip()
    characters = [
        item for item in _extract_list_items(text, "Characters")
        if item not in {"_None listed._", "_None._"}
    ]
    relationship_changes = [
        item for item in _extract_list_items(text, "Relationship Changes")
        if item not in {"_None listed._", "_None._"}
    ]
    key_dialogue = [
        item for item in _extract_list_items(text, "Key Dialogue")
        if item not in {"_None listed._", "_None._"}
    ]
    future_impact = _extract_section_body(text, "Future Impact").strip()
    if future_impact == "_None recorded._":
        future_impact = ""
    return SceneState(
        scene_id=path.stem,
        chapter=chapter,
        page=page,
        scene_description=scene_description,
        mood=mood,
        narrative_summary=narrative,
        characters=characters,
        relationship_changes=relationship_changes,
        key_dialogue=key_dialogue,
        future_impact=future_impact,
    )


def _parse_term_md(path: Path) -> TermState | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m_jp = re.search(r"Term \(JP\):\s*(.+)", text)
    m_zh = re.search(r"Term \(ZH\):\s*(.+)", text)
    m_freq = re.search(r"Frequency:\s*(\d+)", text)
    m_pending = re.search(r"Pending Human Review:\s*(.+)", text)
    m_cult = re.search(r"Cultural Weight:\s*(.+)", text)
    m_strat = re.search(r"Strategy:\s*(.+)", text)
    rejected_reasons: dict[str, str] = {}
    for item in _extract_list_items(text, "Rejected Reasons"):
        if ":" in item:
            candidate, reason = item.split(":", 1)
            rejected_reasons[candidate.strip()] = reason.strip()
        elif item:
            rejected_reasons[item] = ""
    context = "\n".join(
        line
        for line in _extract_section_body(text, "Context").splitlines()
        if line.strip()
        and not line.strip().startswith("- ")
        and line.strip() != "_No context provided._"
    ).strip()
    return TermState(
        term_id=path.stem,
        term_jp=m_jp.group(1).strip() if m_jp else "",
        term_zh=m_zh.group(1).strip() if m_zh else "",
        candidate_translations=_extract_list_items(text, "Candidate Translations"),
        context=context,
        cultural_weight=m_cult.group(1).strip() if m_cult else "",
        strategy=m_strat.group(1).strip() if m_strat else "",
        accepted_reason=_extract_section_body(text, "Accepted Reason").strip(),
        rejected_reasons=rejected_reasons,
        applicability_scope=_extract_section_body(text, "Applicability Scope").strip(),
        provenance=_parse_key_value_section(text, "Provenance"),
        pending_human_review=(
            m_pending.group(1).strip().lower() == "true"
            if m_pending else False
        ),
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
    m_input = re.search(r"Input Ref:\s*(.+)", text)
    return DecisionState(
        decision_id=path.stem,
        stage=m_stage.group(1).strip() if m_stage else "",
        input_ref=m_input.group(1).strip() if m_input else "",
        decision=_extract_decision_body(text),
        rationale=_clean_placeholder_body(
            _extract_section_body(text, "Rationale"),
            "_No rationale provided._",
        ),
        confidence=float(m_conf.group(1)) if m_conf else 0.0,
        metadata=_parse_metadata_section(text),
        timestamp=m_ts.group(1).strip() if m_ts else "",
    )


def _extract_decision_body(text: str) -> str:
    body = _extract_section_body(text, "Decision")
    lines: list[str] = []
    metadata_prefixes = ("- Stage:", "- Confidence:", "- Timestamp:", "- Input Ref:")
    for line in body.splitlines():
        if line.strip().startswith(metadata_prefixes):
            break
        lines.append(line)
    return _clean_placeholder_body("\n".join(lines), "_No decision recorded._")


def _clean_placeholder_body(body: str, placeholder: str) -> str:
    value = body.strip()
    return "" if value == placeholder else value


def _parse_metadata_section(text: str) -> dict[str, object]:
    section = re.search(r"## Metadata\n(.+?)(?:\n## |\Z)", text, re.S)
    if not section:
        return {}

    metadata: dict[str, object] = {}
    for line in section.group(1).splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, value = stripped[2:].split(":", 1)
        raw_value = value.strip()
        if raw_value.startswith(("{", "[")):
            try:
                metadata[key.strip()] = json.loads(raw_value)
                continue
            except json.JSONDecodeError:
                pass
        metadata[key.strip()] = raw_value
    return metadata


def _parse_key_value_section(text: str, heading: str) -> dict[str, object]:
    body = _extract_section_body(text, heading)
    values: dict[str, object] = {}
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped.startswith("- ") or ":" not in stripped:
            continue
        key, value = stripped[2:].split(":", 1)
        raw_value = value.strip()
        if raw_value.startswith(("{", "[")):
            try:
                values[key.strip()] = json.loads(raw_value)
                continue
            except json.JSONDecodeError:
                pass
        values[key.strip()] = raw_value
    return values
