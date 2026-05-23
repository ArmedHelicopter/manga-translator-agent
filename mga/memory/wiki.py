"""WikiProjection: generate Markdown wiki pages from structured state."""

from __future__ import annotations

from pathlib import Path

from mga.memory.entities import (
    CharacterState,
    DecisionState,
    MemoryIndex,
    SceneState,
    TermState,
)

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
        if character.voice_evolutions:
            lines.append("")
            lines.append("## Voice Evolutions")
            for evo in character.voice_evolutions:
                chapter = evo.get("chapter", "?")
                note = evo.get("note", "")
                lines.append(f"- ch{chapter}: {note}")
        if character.provenance:
            lines.append("")
            lines.append("## Provenance")
            for key, val in character.provenance.items():
                lines.append(f"- {key}: {val}")
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
            f"- Frequency: {term.frequency}",
            "",
            "## Context",
            term.context or "_No context provided._",
            "",
            f"- Cultural Weight: {term.cultural_weight}",
            f"- Strategy: {term.strategy}",
        ]
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
    def write_all(project_dir: Path, index: MemoryIndex) -> None:
        """Write all wiki Markdown files to memory/<section>/."""
        from mga.memory.state import StateManager

        base = project_dir / "memory"
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
        for section, (id_map, gen_fn) in _GENERATORS.items():
            out_dir = base / section
            out_dir.mkdir(parents=True, exist_ok=True)
            for eid, _label in id_map.items():
                entity = _GETTERS[section](project_dir, eid)
                if entity:
                    (out_dir / f"{eid}.md").write_text(gen_fn(entity), encoding="utf-8")
        # index page
        idx_dir = base / "indexes"
        idx_dir.mkdir(parents=True, exist_ok=True)
        (idx_dir / "index.md").write_text(
            WikiProjection.generate_index(index), encoding="utf-8",
        )
