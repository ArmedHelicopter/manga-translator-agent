"""MemoryRetrieval: keyword search and context extraction across memory entities."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mga.memory.entities import (
    CharacterState,
    DecisionState,
    SceneState,
    TermState,
)
from mga.memory.state import StateManager


def _text_dump(obj: Any) -> str:
    """Flatten a Pydantic model or dict into searchable plain text."""
    if hasattr(obj, "model_dump"):
        parts: list[str] = []
        for val in obj.model_dump().values():
            if isinstance(val, str):
                parts.append(val)
            elif isinstance(val, list):
                parts.append(" ".join(str(v) for v in val))
            elif isinstance(val, dict):
                parts.append(" ".join(str(v) for v in val.values()))
        return " ".join(parts)
    return str(obj)


def _match(query: str, text: str) -> bool:
    """Case-insensitive substring match."""
    return query.lower() in text.lower()


class MemoryRetrieval:
    """Search and extract context from structured memory state."""

    @staticmethod
    def search(
        project_dir: Path,
        query: str,
        entity_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Keyword search across all entities. Returns list of matches."""
        results: list[dict[str, Any]] = []
        types = entity_types or ["characters", "scenes", "terms", "decisions"]

        if "characters" in types:
            for ch in StateManager.list_characters(project_dir):
                if _match(query, _text_dump(ch)):
                    results.append({"type": "character", "entity": ch})

        if "scenes" in types:
            for sc in StateManager.list_scenes(project_dir):
                if _match(query, _text_dump(sc)):
                    results.append({"type": "scene", "entity": sc})

        if "terms" in types:
            for tm in StateManager.list_terms(project_dir):
                if _match(query, _text_dump(tm)):
                    results.append({"type": "term", "entity": tm})

        if "decisions" in types:
            for dc in StateManager.list_decisions(project_dir):
                if _match(query, _text_dump(dc)):
                    results.append({"type": "decision", "entity": dc})

        return results

    @staticmethod
    def get_character_context(
        project_dir: Path,
        character_id: str,
        chapter: int | None = None,
    ) -> dict[str, Any]:
        """Return speech patterns, catchphrases, tone for prompt injection."""
        ch = StateManager.get_character(project_dir, character_id)
        if ch is None:
            return {}
        ctx: dict[str, Any] = {
            "character_id": ch.character_id,
            "name_jp": ch.name_jp,
            "name_zh": ch.name_zh,
            "speech_patterns": ch.speech_patterns,
            "catchphrases": ch.catchphrases,
            "tone_spectrum": ch.tone_spectrum,
            "translation_notes": ch.translation_notes,
        }
        if chapter is not None and ch.voice_evolutions:
            ctx["voice_evolutions"] = [
                e for e in ch.voice_evolutions if e.get("chapter", 0) <= chapter
            ]
        return ctx

    @staticmethod
    def get_scene_context(
        project_dir: Path,
        chapter: int,
        page: int,
    ) -> dict[str, Any]:
        """Return scene summary and character info for a given page."""
        for sc in StateManager.list_scenes(project_dir):
            if sc.chapter == chapter and sc.page == page:
                ctx: dict[str, Any] = {
                    "scene_id": sc.scene_id,
                    "mood": sc.mood,
                    "narrative_summary": sc.narrative_summary,
                    "scene_description": sc.scene_description,
                    "characters": [],
                }
                for cid in sc.characters:
                    ch = StateManager.get_character(project_dir, cid)
                    if ch:
                        ctx["characters"].append({
                            "character_id": ch.character_id,
                            "name_jp": ch.name_jp,
                            "name_zh": ch.name_zh,
                            "speech_patterns": ch.speech_patterns,
                        })
                return ctx
        return {}
