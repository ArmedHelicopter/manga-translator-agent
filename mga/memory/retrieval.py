"""MemoryRetrieval: keyword search and context extraction across memory entities."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from mga.memory.entities import (
    CharacterState,
    DecisionState,
    SceneState,
    TermState,
)
from mga.memory.state import StateManager


_PROFILE_METADATA_KEYS = (
    "last_reviewed_by",
    "last_reviewed_at",
    "last_reviewed_chapter",
    "confidence",
    "staleness_threshold",
)


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


def _matching_index_ids(query: str, entries: dict[str, str]) -> list[str]:
    """Return index IDs whose ID or label matches the query."""
    return [
        entity_id for entity_id, label in entries.items()
        if _match(query, entity_id) or _match(query, label)
    ]


def _append_result(
    results: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    entity_type: str,
    entity_id: str,
    entity: Any,
) -> None:
    key = (entity_type, entity_id)
    if key in seen:
        return
    seen.add(key)
    results.append({"type": entity_type, "entity": entity})


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
        seen: set[tuple[str, str]] = set()
        types = entity_types or ["characters", "scenes", "terms", "decisions"]
        index = StateManager.load(project_dir)

        if "characters" in types:
            for character_id in _matching_index_ids(query, index.characters):
                ch = StateManager.get_character(project_dir, character_id)
                if ch is not None:
                    _append_result(results, seen, "character", character_id, ch)
            for ch in StateManager.list_characters(project_dir):
                if _match(query, _text_dump(ch)):
                    _append_result(results, seen, "character", ch.character_id, ch)

        if "scenes" in types:
            for scene_id in _matching_index_ids(query, index.scenes):
                sc = StateManager.get_scene(project_dir, scene_id)
                if sc is not None:
                    _append_result(results, seen, "scene", scene_id, sc)
            for sc in StateManager.list_scenes(project_dir):
                if _match(query, _text_dump(sc)):
                    _append_result(results, seen, "scene", sc.scene_id, sc)

        if "terms" in types:
            for term_id in _matching_index_ids(query, index.terms):
                tm = StateManager.get_term(project_dir, term_id)
                if tm is not None:
                    _append_result(results, seen, "term", term_id, tm)
            for tm in StateManager.list_terms(project_dir):
                if _match(query, _text_dump(tm)):
                    _append_result(results, seen, "term", tm.term_id, tm)

        if "decisions" in types:
            for decision_id in _matching_index_ids(query, index.decisions):
                dc = StateManager.get_decision(project_dir, decision_id)
                if dc is not None:
                    _append_result(results, seen, "decision", decision_id, dc)
            for dc in StateManager.list_decisions(project_dir):
                if _match(query, _text_dump(dc)):
                    _append_result(results, seen, "decision", dc.decision_id, dc)

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
            from mga.memory.profile_loader import load_character_profile

            ch = load_character_profile(project_dir, character_id)
        if ch is None:
            return {}
        ctx = _character_context(ch)
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
                    "relationship_changes": sc.relationship_changes,
                    "key_dialogue": sc.key_dialogue,
                    "future_impact": sc.future_impact,
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

    @staticmethod
    def get_recent_translations(
        project_dir: Path,
        speakers: list[str] | None = None,
        limit: int = 5,
    ) -> dict[str, list[str]]:
        """Return recent translated lines grouped by speaker."""
        translations_dir = project_dir / "translations"
        if not translations_dir.exists():
            return {}

        speaker_filter = set(speakers or [])
        grouped: dict[str, list[str]] = {}
        for path in sorted(translations_dir.rglob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(payload, dict):
                continue

            translations = {
                str(item.get("bubble_id")): str(item.get("text", ""))
                for item in payload.get("translations", [])
                if isinstance(item, dict) and item.get("bubble_id") and item.get("text")
            }
            for bubble in payload.get("bubbles", []):
                if not isinstance(bubble, dict):
                    continue
                speaker = bubble.get("speaker_id") or bubble.get("speaker_name")
                bubble_id = bubble.get("bubble_id")
                if not speaker or not bubble_id:
                    continue
                speaker = str(speaker)
                if speaker_filter and speaker not in speaker_filter:
                    continue
                text = translations.get(str(bubble_id))
                if text:
                    grouped.setdefault(speaker, []).append(text)

        return {
            speaker: lines[-limit:]
            for speaker, lines in grouped.items()
            if lines
        }

    @staticmethod
    def search_translation_memory(
        project_dir: Path,
        query: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Return reusable translation-memory examples matching source text."""
        scored: list[dict[str, Any]] = []
        for entry in _iter_translation_history_entries(project_dir):
            score = _translation_memory_score(query, entry)
            if score <= 0:
                continue
            scored.append({**entry, "score": score})
        scored.sort(
            key=lambda item: (
                -item["score"],
                str(item.get("page_id", "")),
                int(item.get("reading_order", 0) or 0),
                str(item.get("bubble_id", "")),
            )
        )
        return scored[:limit]

    @staticmethod
    def format_translation_memory_context(entries: list[dict[str, Any]]) -> str:
        """Format translation-memory examples for prompt injection."""
        if not entries:
            return ""
        lines = ["## Translation Memory"]
        for entry in entries:
            source = str(entry.get("source_text") or "")
            target = str(entry.get("translated_text") or "")
            page_id = str(entry.get("page_id") or "")
            bubble_id = str(entry.get("bubble_id") or "")
            speaker = str(entry.get("speaker_id") or entry.get("speaker_name") or "")
            label = f"- {page_id}/{bubble_id}"
            if speaker:
                label += f" speaker={speaker}"
            label += f" score={entry.get('score', 0)}"
            lines.append(label)
            lines.append(f"  source: {source}")
            lines.append(f"  translation: {target}")
        return "\n".join(lines)

    @staticmethod
    def get_profile_warnings(
        project_dir: Path,
        speakers: list[str] | None = None,
        current_chapter: int | None = None,
    ) -> list[dict[str, Any]]:
        """Return advisory profile maintenance warnings for active speakers."""
        if current_chapter is None:
            return []

        warnings: list[dict[str, Any]] = []
        for speaker in speakers or []:
            profile = StateManager.get_character(project_dir, speaker)
            if profile is None:
                from mga.memory.profile_loader import load_character_profile

                profile = load_character_profile(project_dir, speaker)
            if profile is None:
                continue

            metadata = profile.provenance or {}
            reviewed_chapter = _coerce_int(metadata.get("last_reviewed_chapter"))
            threshold = _coerce_int(metadata.get("staleness_threshold"))
            if reviewed_chapter is None or threshold is None:
                continue
            age = current_chapter - reviewed_chapter
            if age <= threshold:
                continue

            warning: dict[str, Any] = {
                "character_id": speaker,
                "category": "character.profile_stale",
                "current_chapter": current_chapter,
                "last_reviewed_chapter": reviewed_chapter,
                "staleness_threshold": threshold,
                "message": f"Character profile for {speaker} is stale by {age} chapters",
            }
            if "confidence" in metadata:
                warning["confidence"] = metadata["confidence"]
            if "last_reviewed_at" in metadata:
                warning["last_reviewed_at"] = metadata["last_reviewed_at"]
            warnings.append(warning)

        return warnings


def _character_context(ch: CharacterState) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "character_id": ch.character_id,
        "name_jp": ch.name_jp,
        "name_zh": ch.name_zh,
        "archetype": ch.archetype,
        "speech_patterns": ch.speech_patterns,
        "catchphrases": ch.catchphrases,
        "tone_spectrum": ch.tone_spectrum,
        "translation_notes": ch.translation_notes,
        "relationship_speech": ch.relationship_speech,
    }
    profile_metadata = {
        key: ch.provenance[key]
        for key in _PROFILE_METADATA_KEYS
        if key in ch.provenance
    }
    if profile_metadata:
        ctx["profile_metadata"] = profile_metadata
    if ch.voice_evolutions:
        ctx["voice_evolutions"] = ch.voice_evolutions
    return ctx


def _iter_translation_history_entries(project_dir: Path) -> list[dict[str, Any]]:
    translations_dir = project_dir / "translations"
    if not translations_dir.exists():
        return []

    entries: list[dict[str, Any]] = []
    for path in sorted(translations_dir.rglob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(payload, dict):
            continue
        translations = {
            str(item.get("bubble_id")): item
            for item in payload.get("translations", [])
            if isinstance(item, dict) and item.get("bubble_id")
        }
        for bubble in payload.get("bubbles", []):
            if not isinstance(bubble, dict):
                continue
            bubble_id = str(bubble.get("bubble_id") or "")
            translated = translations.get(bubble_id)
            if not bubble_id or not translated:
                continue
            source_text = str(bubble.get("source_text") or "")
            translated_text = str(translated.get("text") or "")
            if not source_text or not translated_text:
                continue
            entries.append({
                "page_id": str(payload.get("page_id") or path.stem),
                "page_index": payload.get("page_index", 0),
                "bubble_id": bubble_id,
                "source_text": source_text,
                "translated_text": translated_text,
                "speaker_id": bubble.get("speaker_id") or "",
                "speaker_name": bubble.get("speaker_name") or "",
                "reading_order": bubble.get("reading_order", 0),
                "path": path.relative_to(project_dir).as_posix(),
            })
    return entries


def _translation_memory_score(query: str, entry: dict[str, Any]) -> int:
    query_norm = _normalize_memory_text(query)
    if not query_norm:
        return 0
    source = _normalize_memory_text(str(entry.get("source_text") or ""))
    target = _normalize_memory_text(str(entry.get("translated_text") or ""))
    score = 0
    if query_norm == source:
        score += 100
    elif query_norm in source or source in query_norm:
        score += 60
    query_tokens = set(_memory_tokens(query_norm))
    source_tokens = set(_memory_tokens(source))
    target_tokens = set(_memory_tokens(target))
    if query_tokens:
        score += len(query_tokens & source_tokens) * 10
        score += len(query_tokens & target_tokens) * 3
    return score


def _normalize_memory_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold()).strip()


def _memory_tokens(value: str) -> list[str]:
    return re.findall(r"\w+", value)


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None
