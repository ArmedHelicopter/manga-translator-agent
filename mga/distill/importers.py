"""Importers for community formats back into memory system.

Supports:
- Character Card: TavernAI/SillyTavern → memory profile
- Lorebook: NovelAI/AI Dungeon → memory terms/scenes
"""

from __future__ import annotations

import json
from pathlib import Path

from mga.memory.service import MemoryService, CharacterProfile, TermEntry, SceneContext
from mga.memory.state import StateManager
from mga.memory.entities import CharacterState, TermState, SceneState

from .character_card import CharacterCard
from .lorebook import Lorebook, LorebookEntry


class CharacterCardImporter:
    """Import TavernAI/SillyTavern character cards into memory system."""

    def __init__(self, project_dir: Path | str):
        self.project_dir = Path(project_dir)
        self._memory = None

    @property
    def memory(self) -> MemoryService:
        """Lazy-load memory service."""
        if self._memory is None:
            self._memory = MemoryService(self.project_dir)
            self._memory.initialize()
        return self._memory

    def import_card(self, card: CharacterCard | str | Path) -> CharacterProfile:
        """Import a character card into memory.

        Args:
            card: CharacterCard instance, JSON string, or file path

        Returns:
            Created or updated CharacterProfile
        """
        if isinstance(card, (str, Path)):
            card = self._load_card(card)

        # Extract profile from card
        profile = self._card_to_profile(card)

        # Save to memory
        character_id = self._sanitize_id(card.name)
        self.memory.update_character(
            character_id,
            name_jp=self._extract_jp_name(card.description),
            name_zh=card.name,
            archetype=self._extract_archetype(card.personality),
            speech_patterns=self._extract_speech_patterns(card.personality),
            catchphrases=self._extract_catchphrases(card.mes_example),
        )

        return self.memory.get_character(character_id)

    def import_file(self, card_path: Path | str) -> CharacterProfile:
        """Import a character card from file."""
        card_path = Path(card_path)
        data = json.loads(card_path.read_text(encoding="utf-8"))
        card = CharacterCard(**data)
        return self.import_card(card)

    def import_directory(self, dir_path: Path | str) -> list[CharacterProfile]:
        """Import all character cards from a directory."""
        dir_path = Path(dir_path)
        profiles = []
        for card_path in dir_path.glob("*.json"):
            try:
                profile = self.import_file(card_path)
                profiles.append(profile)
            except Exception as e:
                # Skip invalid cards
                continue
        return profiles

    def _load_card(self, card: str | Path) -> CharacterCard:
        """Load card from string or path."""
        if isinstance(card, Path):
            data = json.loads(card.read_text(encoding="utf-8"))
        else:
            data = json.loads(card)
        return CharacterCard(**data)

    def _card_to_profile(self, card: CharacterCard) -> dict:
        """Convert card fields to profile dict."""
        return {
            "name_zh": card.name,
            "name_jp": self._extract_jp_name(card.description),
            "archetype": self._extract_archetype(card.personality),
            "speech_patterns": self._extract_speech_patterns(card.personality),
            "catchphrases": self._extract_catchphrases(card.mes_example),
        }

    def _sanitize_id(self, name: str) -> str:
        """Create valid character ID from name."""
        import re
        safe = re.sub(r'[^a-zA-Z0-9_-]', '_', name.lower())
        return safe or "character"

    def _extract_jp_name(self, text: str) -> str:
        """Extract Japanese name from description."""
        import re
        match = re.search(r'日文名[:：]\s*(.+)', text)
        return match.group(1).strip() if match else ""

    def _extract_archetype(self, text: str) -> str:
        """Extract archetype from personality."""
        import re
        # Try both patterns: "原型" or "角色原型"
        match = re.search(r'角色原型[:：]\s*(.+)', text)
        if not match:
            match = re.search(r'原型[:：]\s*(.+)', text)
        return match.group(1).strip() if match else ""

    def _extract_speech_patterns(self, text: str) -> dict[str, str]:
        """Extract speech patterns from personality."""
        patterns = {}
        import re
        for match in re.finditer(r'说话模式[:：]\s*(.+)', text):
            pattern_text = match.group(1).strip()
            for part in pattern_text.split(';'):
                if '=' in part:
                    k, v = part.split('=', 1)
                    patterns[k.strip()] = v.strip()
        return patterns

    def _extract_catchphrases(self, text: str) -> list[str]:
        """Extract catchphrases from example dialogue."""
        import re
        phrases = []
        for match in re.finditer(r'"([^"]+)"', text):
            phrases.append(match.group(1))
        return phrases[:5]  # Limit to 5 catchphrases


class LorebookImporter:
    """Import NovelAI/AI Dungeon lorebook into memory system."""

    def __init__(self, project_dir: Path | str):
        self.project_dir = Path(project_dir)
        self._memory = None

    @property
    def memory(self) -> MemoryService:
        """Lazy-load memory service."""
        if self._memory is None:
            self._memory = MemoryService(self.project_dir)
            self._memory.initialize()
        return self._memory

    def import_lorebook(self, lorebook: Lorebook | str | Path) -> dict[str, int]:
        """Import a lorebook into memory.

        Args:
            lorebook: Lorebook instance, JSON string, or file path

        Returns:
            Statistics: {"characters": n, "terms": n, "scenes": n}
        """
        if isinstance(lorebook, (str, Path)):
            lorebook = self._load_lorebook(lorebook)

        stats = {"characters": 0, "terms": 0, "scenes": 0}

        for entry in lorebook.entries:
            lore_key = entry.loreKey or ""
            if lore_key.startswith("character:"):
                self._import_character_entry(entry)
                stats["characters"] += 1
            elif lore_key.startswith("term:"):
                self._import_term_entry(entry)
                stats["terms"] += 1
            elif lore_key.startswith("scene:"):
                self._import_scene_entry(entry)
                stats["scenes"] += 1
            else:
                # Default: import as term
                self._import_term_entry(entry)
                stats["terms"] += 1

        return stats

    def import_file(self, lorebook_path: Path | str) -> dict[str, int]:
        """Import a lorebook from file."""
        lorebook_path = Path(lorebook_path)
        data = json.loads(lorebook_path.read_text(encoding="utf-8"))
        lorebook = Lorebook(**data)
        return self.import_lorebook(lorebook)

    def _load_lorebook(self, lorebook: str | Path) -> Lorebook:
        """Load lorebook from string or path."""
        if isinstance(lorebook, Path):
            data = json.loads(lorebook.read_text(encoding="utf-8"))
        else:
            data = json.loads(lorebook)
        return Lorebook(**data)

    def _import_character_entry(self, entry: LorebookEntry) -> None:
        """Import a character lorebook entry."""
        character_id = entry.loreKey.replace("character:", "")
        name = self._extract_title(entry.entry)

        self.memory.get_or_create_character(character_id)
        self.memory.update_character(
            character_id,
            name_zh=name,
            name_jp=self._extract_field(entry.entry, "日文名"),
            archetype=self._extract_field(entry.entry, "角色类型"),
            speech_patterns=self._extract_patterns(entry.entry),
            catchphrases=self._extract_catchphrases_from_entry(entry.entry),
        )

    def _import_term_entry(self, entry: LorebookEntry) -> None:
        """Import a term lorebook entry."""
        term_id = entry.loreKey.replace("term:", "") if ":" in entry.loreKey else entry.key[0] if entry.key else "unknown"

        term_jp = self._extract_title(entry.entry)
        term_zh = self._extract_field(entry.entry, "翻译")

        if term_jp and term_zh:
            self.memory.register_term(
                term_jp=term_jp,
                term_zh=term_zh,
                context=self._extract_field(entry.entry, "语境"),
                strategy=self._extract_field(entry.entry, "策略"),
            )

    def _import_scene_entry(self, entry: LorebookEntry) -> None:
        """Import a scene lorebook entry."""
        scene_id = entry.loreKey.replace("scene:", "") if ":" in entry.loreKey else entry.key[0] if entry.key else "unknown"

        chapter = self._extract_int(entry.entry, "章节")
        page = self._extract_int(entry.entry, "页码")

        scene = self.memory.get_or_create_scene(scene_id)
        self.memory.update_scene(
            scene_id,
            chapter=chapter,
            page=page,
            description=self._extract_field(entry.entry, "场景描述"),
            mood=self._extract_field(entry.entry, "氛围"),
            summary=self._extract_field(entry.entry, "叙述"),
        )

    def _extract_title(self, text: str) -> str:
        """Extract title from markdown entry."""
        import re
        match = re.search(r'^#\s*(.+)$', text, re.MULTILINE)
        return match.group(1).strip() if match else text.split('\n')[0][:50]

    def _extract_field(self, text: str, field_name: str) -> str:
        """Extract field value from entry text."""
        import re
        match = re.search(rf'{field_name}[:：]\s*(.+)', text)
        return match.group(1).strip() if match else ""

    def _extract_int(self, text: str, field_name: str) -> int:
        """Extract integer field value."""
        value = self._extract_field(text, field_name)
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    def _extract_patterns(self, text: str) -> dict[str, str]:
        """Extract speech patterns from text."""
        patterns = {}
        import re
        match = re.search(r'说话模式[:：]\s*(.+)', text)
        if match:
            pattern_text = match.group(1).strip()
            for part in pattern_text.split(';'):
                if '=' in part:
                    k, v = part.split('=', 1)
                    patterns[k.strip()] = v.strip()
        return patterns

    def _extract_catchphrases_from_entry(self, text: str) -> list[str]:
        """Extract catchphrases from entry text."""
        import re
        phrases = []
        match = re.search(r'口头禅[:：]\s*(.+)', text)
        if match:
            catch_text = match.group(1).strip()
            for phrase in catch_text.split(','):
                phrase = phrase.strip()
                if phrase:
                    phrases.append(phrase)
        return phrases[:5]


class HermesSkillImporter:
    """Import/Export Hermes agent skill format.

    Note: Hermes skill format is not yet standardized.
    This is a placeholder interface for future implementation.
    """

    def __init__(self, project_dir: Path | str):
        self.project_dir = Path(project_dir)

    def export_skill(self, character_id: str) -> dict:
        """Export character as Hermes skill format.

        Returns a placeholder skill definition.
        """
        from mga.memory.service import MemoryService

        memory = MemoryService(self.project_dir)
        memory.initialize()
        profile = memory.get_character(character_id)

        if profile is None:
            raise ValueError(f"Character not found: {character_id}")

        return {
            "name": f"act_as_{character_id}",
            "description": f"Act as character {profile.name_zh or character_id}",
            "instruction": self._build_instruction(profile),
            "variables": {
                "character_name": profile.name_zh or profile.name_jp or character_id,
                "archetype": profile.archetype,
            },
        }

    def _build_instruction(self, profile) -> str:
        """Build skill instruction from profile."""
        parts = [f"You are {profile.name_zh or profile.name_jp or profile.character_id}."]

        if profile.archetype:
            parts.append(f"Character type: {profile.archetype}.")
        if profile.speech_patterns:
            patterns = ", ".join(f"{k}: {v}" for k, v in profile.speech_patterns.items())
            parts.append(f"Speech patterns: {patterns}.")
        if profile.catchphrases:
            phrases = ", ".join(profile.catchphrases[:3])
            parts.append(f"Catchphrases: {phrases}.")

        return " ".join(parts)

    def import_skill(self, skill_data: dict) -> str:
        """Import Hermes skill into memory.

        Returns:
            Created character_id
        """
        from mga.memory.service import MemoryService

        memory = MemoryService(self.project_dir)
        memory.initialize()

        char_id = skill_data.get("name", "unknown").replace("act_as_", "")
        character_id = memory.get_or_create_character(char_id).character_id

        # Extract profile from instruction
        instruction = skill_data.get("instruction", "")

        memory.update_character(
            character_id,
            name_zh=skill_data.get("variables", {}).get("character_name", ""),
            archetype=skill_data.get("variables", {}).get("archetype", ""),
        )

        return character_id