"""Lorebook exporter for NovelAI/AI Dungeon format.

NovelAI format specification:
- JSON with entries array, loreKey, entry, key, case_sensitive, priority, constant, selective, uid
- AI Dungeon format: similar key-value structure

Priority levels:
- 0: lowest (context-sensitive)
- 100: highest (always active)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class LorebookEntry(BaseModel):
    """Single lorebook entry in NovelAI format."""

    loreKey: str = ""
    entry: str = ""
    key: list[str] = Field(default_factory=list)
    case_sensitive: bool = False
    priority: int = 0
    constant: bool = False
    selective: bool = True
    uid: str = ""

    def __init__(self, **data):
        # Auto-generate uid if not provided
        if "uid" not in data or not data["uid"]:
            data["uid"] = str(uuid4())[:8]
        super().__init__(**data)

    def to_dict(self) -> dict[str, Any]:
        return {
            "loreKey": self.loreKey,
            "entry": self.entry,
            "key": self.key,
            "case_sensitive": self.case_sensitive,
            "priority": self.priority,
            "constant": self.constant,
            "selective": self.selective,
            "uid": self.uid,
        }


class Lorebook(BaseModel):
    """NovelAI/AI Dungeon lorebook format container."""

    entries: list[LorebookEntry] = Field(default_factory=list)
    version: int = 1
    created_at: str = ""

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.model_dump(exclude_none=True), ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, data: str | dict) -> "Lorebook":
        if isinstance(data, str):
            data = json.loads(data)
        return cls(**data)


class LorebookExporter:
    """Export memory terms, characters, and scenes to NovelAI lorebook format."""

    def __init__(self, project_dir: Path | str):
        self.project_dir = Path(project_dir)
        self._memory = None

    @property
    def memory(self):
        """Lazy-load memory service."""
        from mga.memory.service import MemoryService
        if self._memory is None:
            self._memory = MemoryService(self.project_dir)
            self._memory.initialize()
        return self._memory

    def export_character_entry(self, character_id: str) -> LorebookEntry:
        """Export a character as lorebook entry."""
        profile = self.memory.get_character(character_id)
        if profile is None:
            raise ValueError(f"Character not found: {character_id}")

        name = profile.name_zh or profile.name_jp or character_id

        # Build entry content
        parts = [f"# {name}"]
        if profile.name_jp:
            parts.append(f"日文名: {profile.name_jp}")
        if profile.name_zh:
            parts.append(f"中文名: {profile.name_zh}")
        if profile.archetype:
            parts.append(f"角色类型: {profile.archetype}")
        if profile.speech_patterns:
            patterns = "; ".join(f"{k}={v}" for k, v in profile.speech_patterns.items())
            parts.append(f"说话模式: {patterns}")
        if profile.catchphrases:
            parts.append(f"口头禅: {', '.join(profile.catchphrases)}")

        entry_text = "\n".join(parts)

        # Keys for triggering this entry
        keys = []
        if profile.name_jp:
            keys.append(profile.name_jp)
        if profile.name_zh:
            keys.append(profile.name_zh)
        keys.append(character_id)

        return LorebookEntry(
            loreKey=f"character:{character_id}",
            entry=entry_text,
            key=keys,
            priority=80,  # High priority for characters
            constant=False,
        )

    def export_term_entry(self, term_id: str) -> LorebookEntry:
        """Export a terminology entry."""
        term = self.memory.get_term(term_id)
        if term is None:
            raise ValueError(f"Term not found: {term_id}")

        parts = [f"# {term.term_jp}"]
        parts.append(f"翻译: {term.term_zh}")
        if term.context:
            parts.append(f"语境: {term.context}")
        if term.strategy:
            parts.append(f"策略: {term.strategy}")

        entry_text = "\n".join(parts)

        # Frequency-based priority
        priority = min(50 + term.frequency * 5, 90)

        return LorebookEntry(
            loreKey=f"term:{term_id}",
            entry=entry_text,
            key=[term.term_jp],
            priority=priority,
            constant=False,
        )

    def export_scene_entry(self, scene_id: str) -> LorebookEntry:
        """Export a scene as lorebook entry."""
        scene = self.memory.get_scene(scene_id)
        if scene is None:
            raise ValueError(f"Scene not found: {scene_id}")

        parts = [f"# Scene {scene_id}"]

        if scene.chapter:
            parts.append(f"章节: {scene.chapter}")
        if scene.page:
            parts.append(f"页码: {scene.page}")
        if scene.description:
            parts.append(f"场景描述: {scene.description}")
        if scene.mood:
            parts.append(f"氛围: {scene.mood}")
        if scene.summary:
            parts.append(f"叙述: {scene.summary}")
        if scene.characters:
            parts.append(f"出场角色: {', '.join(scene.characters)}")

        entry_text = "\n".join(parts)

        return LorebookEntry(
            loreKey=f"scene:{scene_id}",
            entry=entry_text,
            key=[scene_id, f"ch{scene.chapter}" if scene.chapter else ""],
            priority=30,  # Lower priority for scenes
            constant=False,
        )

    def export_all(self) -> Lorebook:
        """Export all memory entities as lorebook."""
        from datetime import datetime

        entries = []

        # Export characters
        for profile in self.memory.list_characters():
            entry = self.export_character_entry(profile.character_id)
            entries.append(entry)

        # Export terms
        for term_id in list(self.memory._terms.keys()):
            try:
                entry = self.export_term_entry(term_id)
                entries.append(entry)
            except ValueError:
                pass

        # Export scenes
        for scene_id in list(self.memory._scenes.keys()):
            try:
                entry = self.export_scene_entry(scene_id)
                entries.append(entry)
            except ValueError:
                pass

        return Lorebook(
            entries=entries,
            created_at=datetime.now().isoformat(),
        )

    def save(
        self,
        output_path: Path | str,
        format: str = "json",
    ) -> Path:
        """Export lorebook to file.

        Args:
            output_path: Output file path
            format: Output format (json or toml, default json)

        Returns:
            Path to saved file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lorebook = self.export_all()

        if format == "toml":
            try:
                import tomllib
            except ModuleNotFoundError:
                import tomli as tomllib

            content = tomllib.dumps(lorebook.model_dump())
            output_path.write_text(content, encoding="utf-8")
        else:
            content = lorebook.to_json()
            output_path.write_text(content, encoding="utf-8")

        return output_path