"""Unified Memory Service — single entry point for character/scene memory.

This module provides a unified interface to all memory operations:
- Character profiles (load, save, update)
- Scene contexts (load, save, update)
- Relationship graph (build, query)
- Translation memory (search, learn)

Usage:
    from mga.core.memory_service import MemoryService

    service = MemoryService(project_dir)
    profile = service.get_character_profile("akari")
    service.update_character("akari", {"name_zh": "灯里"})
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# === State Manager ===

class StateManager:
    """CRUD operations for memory state entities."""

    @staticmethod
    def upsert_character(project_dir: Path, character: Any) -> None:
        """Create or update a character state."""
        char_dir = project_dir / "memory" / "state" / "characters"
        char_dir.mkdir(parents=True, exist_ok=True)
        path = char_dir / f"{character.character_id}.json"
        data = character.model_dump() if hasattr(character, "model_dump") else dict(character)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def get_character(project_dir: Path, character_id: str) -> dict | None:
        """Load a character state by ID."""
        path = project_dir / "memory" / "state" / "characters" / f"{character_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def upsert_term(project_dir: Path, term: Any) -> None:
        """Create or update a term state."""
        term_dir = project_dir / "memory" / "state" / "terms"
        term_dir.mkdir(parents=True, exist_ok=True)
        path = term_dir / f"{term.term_id}.json"
        data = term.model_dump() if hasattr(term, "model_dump") else dict(term)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def upsert_scene(project_dir: Path, scene: Any) -> None:
        """Create or update a scene state."""
        scene_dir = project_dir / "memory" / "state" / "scenes"
        scene_dir.mkdir(parents=True, exist_ok=True)
        path = scene_dir / f"{scene.page_id}.json"
        data = scene.model_dump() if hasattr(scene, "model_dump") else dict(scene)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def list_characters(project_dir: Path) -> list[str]:
        """List all character IDs."""
        char_dir = project_dir / "memory" / "state" / "characters"
        if not char_dir.exists():
            return []
        return [p.stem for p in char_dir.glob("*.json")]

    @staticmethod
    def load_all_characters(project_dir: Path) -> dict[str, dict]:
        """Load all characters as a dict keyed by ID."""
        chars = {}
        for char_id in StateManager.list_characters(project_dir):
            char = StateManager.get_character(project_dir, char_id)
            if char:
                chars[char_id] = char
        return chars


# === Memory Service ===

class MemoryService:
    """Unified memory service with caching and convenience methods."""

    def __init__(self, project_dir: Path | str = "."):
        self.project_dir = Path(project_dir)
        self._character_cache: dict[str, dict] = {}
        self._scene_cache: dict[str, dict] = {}
        self._graph = None

    def get_character_profile(self, character_id: str) -> dict:
        """Get character profile for prompt injection."""
        if character_id in self._character_cache:
            return self._character_cache[character_id]

        char = StateManager.get_character(self.project_dir, character_id)
        if char:
            self._character_cache[character_id] = char
            return char
        return {}

    def get_all_character_profiles(self) -> dict[str, dict]:
        """Get all character profiles keyed by ID."""
        return StateManager.load_all_characters(self.project_dir)

    def update_character(self, character_id: str, updates: dict) -> None:
        """Update a character with new data."""
        char = self.get_character_profile(character_id) or {}
        char.update(updates)
        char["character_id"] = character_id

        from mga.core.models import CharacterState
        state = CharacterState(**char)
        StateManager.upsert_character(self.project_dir, state)
        self._character_cache[character_id] = char

    def create_character(self, character_id: str, name_jp: str = "", **kwargs) -> None:
        """Create a new character."""
        from datetime import datetime, timezone

        char = {
            "character_id": character_id,
            "name_jp": name_jp,
            "name_zh": kwargs.get("name_zh", name_jp),
            "archetype": kwargs.get("archetype", ""),
            "speech_patterns": kwargs.get("speech_patterns", {}),
            "catchphrases": kwargs.get("catchphrases", []),
            "tone_spectrum": kwargs.get("tone_spectrum", {}),
            "translation_notes": kwargs.get("translation_notes", {}),
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

        from mga.core.models import CharacterState
        state = CharacterState(**char)
        StateManager.upsert_character(self.project_dir, state)
        self._character_cache[character_id] = char

    def get_scene_context(self, page_id: str) -> dict:
        """Get scene context for a page."""
        if page_id in self._scene_cache:
            return self._scene_cache[page_id]

        scene_path = self.project_dir / "memory" / "state" / "scenes" / f"{page_id}.json"
        if scene_path.exists():
            scene = json.loads(scene_path.read_text(encoding="utf-8"))
            self._scene_cache[page_id] = scene
            return scene
        return {}

    def update_scene(self, page_id: str, scene_data: dict) -> None:
        """Update or create a scene."""
        from datetime import datetime, timezone

        scene = self.get_scene_context(page_id) or {}
        scene.update(scene_data)
        scene["page_id"] = page_id
        scene.setdefault("first_seen", datetime.now(timezone.utc).isoformat())
        scene["last_updated"] = datetime.now(timezone.utc).isoformat()

        from mga.core.models import SceneState
        state = SceneState(**scene)
        StateManager.upsert_scene(self.project_dir, state)
        self._scene_cache[page_id] = scene

    def search_translation_memory(
        self,
        source_text: str,
        limit: int = 3,
    ) -> list[dict]:
        """Search for similar translations in memory."""
        # Simple implementation - can be enhanced with embeddings
        results = []
        trans_dir = self.project_dir / "memory" / "translations"
        if not trans_dir.exists():
            return results

        for trans_file in trans_dir.glob("*.json"):
            try:
                trans = json.loads(trans_file.read_text(encoding="utf-8"))
                # Simple text matching
                if source_text in trans.get("source", "") or trans.get("source", "") in source_text:
                    results.append(trans)
                    if len(results) >= limit:
                        break
            except Exception:
                continue

        return results

    def learn_from_translation(
        self,
        character_id: str,
        source_text: str,
        translated_text: str,
    ) -> None:
        """Learn from a translation to update character profile."""
        # Extract patterns from translation
        if len(translated_text) > 100:
            # Too long for catchphrase
            return

        char = self.get_character_profile(character_id)
        if not char:
            return

        # Update catchphrases if this looks like one
        catchphrases = char.get("catchphrases", [])
        if translated_text not in catchphrases and len(catchphrases) < 10:
            catchphrases.append(translated_text)
            self.update_character(character_id, {"catchphrases": catchphrases})

    def invalidate_cache(self) -> None:
        """Clear the in-memory cache."""
        self._character_cache.clear()
        self._scene_cache.clear()


# === Convenience Functions ===

def init_memory(project_dir: Path | str) -> MemoryService:
    """Initialize memory system for a project."""
    project_dir = Path(project_dir)
    memory_dir = project_dir / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    (memory_dir / "state" / "characters").mkdir(parents=True, exist_ok=True)
    (memory_dir / "state" / "terms").mkdir(parents=True, exist_ok=True)
    (memory_dir / "state" / "scenes").mkdir(parents=True, exist_ok=True)
    (memory_dir / "translations").mkdir(parents=True, exist_ok=True)
    return MemoryService(project_dir)


def sync_memory(project_dir: Path | str) -> dict:
    """Sync memory state to wiki projections."""
    service = MemoryService(project_dir)
    result = {
        "characters": len(service.get_all_character_profiles()),
        "scenes": len(service._scene_cache),
    }
    # Wiki sync would go here
    return result


__all__ = [
    "StateManager",
    "MemoryService",
    "init_memory",
    "sync_memory",
]