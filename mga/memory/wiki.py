"""WikiProjection: generate Markdown wiki pages from structured state."""

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


_WORK_SCOPED_SECTIONS = {"scenes", "terms", "decisions"}


def normalize_work_namespace(work: str | None) -> str:
    """Return a path-safe work namespace slug."""
    if not work:
        return ""
    slug = "-".join(re.findall(r"[a-z0-9]+", work.lower()))
    if not slug:
        raise ValueError("work namespace must contain letters or numbers")
    return slug


def work_scoped_id(work: str | None, entity_id: str) -> str:
    """Prefix an entity ID with a normalized work namespace."""
    namespace = normalize_work_namespace(work)
    return f"{namespace}__{entity_id}" if namespace else entity_id


def unscoped_work_id(work: str | None, entity_id: str) -> str:
    namespace = normalize_work_namespace(work)
    prefix = f"{namespace}__"
    return entity_id.removeprefix(prefix) if namespace else entity_id


class WikiProjection:
    """Generate and write Markdown wiki pages from structured memory state."""

    # ── character page ──────────────────────────────────────

    @staticmethod
    def generate_character_page(character: CharacterState) -> str:
        lines = [
            f"# {character.name_jp or character.character_id}",
            "",
            "## Basic Info",
            f"- Character ID: {character.character_id}",
            f"- Name (JP): {character.name_jp}",
            f"- Name (ZH): {character.name_zh}",
            f"- Archetype: {character.archetype}",
            "",
            "## Speech Patterns",
        ]
        for key, val in character.speech_patterns.items():
            lines.append(f"- {key}: {val}")
        if character.catchphrases:
            lines.append("")
            lines.append("## Catchphrases")
            for cp in character.catchphrases:
                lines.append(f"- {cp}")
        if character.tone_spectrum:
            lines.append("")
            lines.append("## Tone Spectrum")
            for key, val in character.tone_spectrum.items():
                lines.append(f"- {key}: {val}")
        if character.translation_notes:
            lines.append("")
            lines.append("## Translation Notes")
            for key, val in character.translation_notes.items():
                lines.append(f"- {key}: {val}")
        if character.relationship_speech:
            lines.append("")
            lines.append("## Relationship Speech")
            for listener, rule in character.relationship_speech.items():
                lines.append(
                    f"- {listener}: "
                    f"{json.dumps(rule, ensure_ascii=False, sort_keys=True)}"
                )
        if character.voice_evolutions:
            lines.append("")
            lines.append("## Voice Evolutions")
            for evo in character.voice_evolutions:
                chapter = evo.get("chapter", "?")
                rendered = json.dumps(evo, ensure_ascii=False, sort_keys=True)
                lines.append(f"- ch{chapter}: {rendered}")
        if character.provenance:
            lines.append("")
            lines.append("## Provenance")
            for key, val in character.provenance.items():
                if isinstance(val, (dict, list)):
                    rendered = json.dumps(val, ensure_ascii=False, sort_keys=True)
                else:
                    rendered = str(val)
                lines.append(f"- {key}: {rendered}")
        return "\n".join(lines) + "\n"

    # ── scene page ──────────────────────────────────────────

    @staticmethod
    def generate_scene_page(scene: SceneState) -> str:
        lines = [
            f"# Scene: ch{scene.chapter} p{scene.page}",
            f"Scene ID: {scene.scene_id}",
            "",
            "## Summary",
            scene.scene_description or "_No description._",
            "",
            f"- Mood: {scene.mood}",
            f"- Narrative: {scene.narrative_summary}",
            "",
            "## Characters",
        ]
        for ch in scene.characters:
            lines.append(f"- {ch}")
        if not scene.characters:
            lines.append("- _None listed._")
        lines.extend(["", "## Relationship Changes"])
        for item in scene.relationship_changes:
            lines.append(f"- {item}")
        if not scene.relationship_changes:
            lines.append("- _None._")
        lines.extend(["", "## Key Dialogue"])
        for item in scene.key_dialogue:
            lines.append(f"- {item}")
        if not scene.key_dialogue:
            lines.append("- _None._")
        lines.extend([
            "",
            "## Future Impact",
            scene.future_impact or "_None recorded._",
        ])
        return "\n".join(lines) + "\n"

    # ── term page ───────────────────────────────────────────

    @staticmethod
    def generate_term_page(term: TermState) -> str:
        lines = [
            f"# {term.term_jp or term.term_id}",
            "",
            "## Basic Info",
            f"- Term ID: {term.term_id}",
            f"- Term (JP): {term.term_jp}",
            f"- Term (ZH): {term.term_zh}",
            f"- Pending Human Review: {term.pending_human_review}",
            f"- Frequency: {term.frequency}",
            "",
            "## Context",
            term.context or "_No context provided._",
            "",
            f"- Cultural Weight: {term.cultural_weight}",
            f"- Strategy: {term.strategy}",
        ]
        if term.candidate_translations:
            lines.extend(["", "## Candidate Translations"])
            for candidate in term.candidate_translations:
                lines.append(f"- {candidate}")
        if term.accepted_reason:
            lines.extend(["", "## Accepted Reason", term.accepted_reason])
        if term.rejected_reasons:
            lines.extend(["", "## Rejected Reasons"])
            for candidate, reason in term.rejected_reasons.items():
                lines.append(f"- {candidate}: {reason}")
        if term.applicability_scope:
            lines.extend(["", "## Applicability Scope", term.applicability_scope])
        if term.provenance:
            lines.extend(["", "## Provenance"])
            for key, val in term.provenance.items():
                if isinstance(val, (dict, list)):
                    rendered = json.dumps(val, ensure_ascii=False, sort_keys=True)
                else:
                    rendered = str(val)
                lines.append(f"- {key}: {rendered}")
        return "\n".join(lines) + "\n"

    # ── decision page ───────────────────────────────────────

    @staticmethod
    def generate_decision_page(decision: DecisionState) -> str:
        lines = [
            f"# Decision: {decision.decision_id}",
            "",
            "## Decision",
            decision.decision or "_No decision recorded._",
            "",
            f"- Stage: {decision.stage}",
            f"- Confidence: {decision.confidence}",
            f"- Timestamp: {decision.timestamp}",
            f"- Input Ref: {decision.input_ref}",
            "",
            "## Rationale",
            decision.rationale or "_No rationale provided._",
        ]
        if decision.metadata:
            lines.extend(["", "## Metadata"])
            for key in sorted(decision.metadata):
                value = decision.metadata[key]
                if isinstance(value, (dict, list)):
                    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
                else:
                    rendered = str(value)
                lines.append(f"- {key}: {rendered}")
        return "\n".join(lines) + "\n"

    # ── index page ──────────────────────────────────────────

    @staticmethod
    def generate_index(index: MemoryIndex) -> str:
        lines = [
            "# Memory Index",
            "",
            f"Version: {index.version}",
            f"Last Updated: {index.last_updated}",
            "",
            "## Characters",
        ]
        for cid, label in index.characters.items():
            lines.append(f"- {label} (`{cid}`)")
        if not index.characters:
            lines.append("- _None._")
        lines.append("")
        lines.append("## Scenes")
        for sid, label in index.scenes.items():
            lines.append(f"- {label} (`{sid}`)")
        if not index.scenes:
            lines.append("- _None._")
        lines.append("")
        lines.append("## Terms")
        for tid, label in index.terms.items():
            lines.append(f"- {label} (`{tid}`)")
        if not index.terms:
            lines.append("- _None._")
        lines.append("")
        lines.append("## Decisions")
        for did, label in index.decisions.items():
            lines.append(f"- {label} (`{did}`)")
        if not index.decisions:
            lines.append("- _None._")
        return "\n".join(lines) + "\n"

    # ── batch write ─────────────────────────────────────────

    @staticmethod
    def write_all(project_dir: Path, index: MemoryIndex, work: str | None = None) -> None:
        """Write all wiki Markdown files to memory/<section>/."""
        from mga.memory.state import StateManager

        base = project_dir / "memory"
        work_namespace = normalize_work_namespace(work)
        _GENERATORS: dict[str, tuple[dict[str, str], callable]] = {
            "characters": (index.characters, WikiProjection.generate_character_page),
            "scenes": (index.scenes, WikiProjection.generate_scene_page),
            "terms": (index.terms, WikiProjection.generate_term_page),
            "decisions": (index.decisions, WikiProjection.generate_decision_page),
        }
        _GETTERS = {
            "characters": StateManager.get_character,
            "scenes": StateManager.get_scene,
            "terms": StateManager.get_term,
            "decisions": StateManager.get_decision,
        }
        filtered_index = MemoryIndex(
            version=index.version,
            last_updated=index.last_updated,
            characters=dict(index.characters),
        )
        for section, (id_map, gen_fn) in _GENERATORS.items():
            out_dir = _wiki_section_dir(base, section, work_namespace)
            out_dir.mkdir(parents=True, exist_ok=True)
            for eid, _label in id_map.items():
                if work_namespace and section in _WORK_SCOPED_SECTIONS:
                    prefix = f"{work_namespace}__"
                    if not eid.startswith(prefix):
                        continue
                entity = _GETTERS[section](project_dir, eid)
                if entity:
                    visible_id = unscoped_work_id(work_namespace, eid)
                    visible_entity = _with_visible_entity_id(section, entity, visible_id)
                    (out_dir / f"{visible_id}.md").write_text(gen_fn(visible_entity), encoding="utf-8")
                    _add_index_entry(filtered_index, section, visible_id, id_map[eid])
        # index page
        idx_dir = base / "indexes"
        idx_dir.mkdir(parents=True, exist_ok=True)
        index_name = f"{work_namespace}.md" if work_namespace else "index.md"
        (idx_dir / index_name).write_text(
            WikiProjection.generate_index(filtered_index if work_namespace else index),
            encoding="utf-8",
        )


def _wiki_section_dir(base: Path, section: str, work_namespace: str) -> Path:
    if work_namespace and section in _WORK_SCOPED_SECTIONS:
        return base / section / work_namespace
    return base / section


def _with_visible_entity_id(section: str, entity, visible_id: str):
    if section == "scenes":
        return entity.model_copy(update={"scene_id": visible_id})
    if section == "terms":
        return entity.model_copy(update={"term_id": visible_id})
    if section == "decisions":
        return entity.model_copy(update={"decision_id": visible_id})
    return entity


def _add_index_entry(index: MemoryIndex, section: str, entity_id: str, label: str) -> None:
    if section == "characters":
        index.characters[entity_id] = label
    elif section == "scenes":
        index.scenes[entity_id] = label
    elif section == "terms":
        index.terms[entity_id] = label
    elif section == "decisions":
        index.decisions[entity_id] = label
