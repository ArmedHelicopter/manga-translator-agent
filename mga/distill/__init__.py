"""Knowledge distillation module for exporting memory to community formats.

Supports:
- Character Card: TavernAI/SillyTavern compatible format
- Lorebook: NovelAI/AI Dungeon compatible format
- Hermes Agent Skill: Hermes-compatible agent skill definition
"""

from __future__ import annotations

from .character_card import CharacterCardExporter, CharacterCard
from .lorebook import LorebookExporter, LorebookEntry, Lorebook
from .importers import CharacterCardImporter, LorebookImporter, HermesSkillImporter, HermesSkill

__all__ = [
    "CharacterCard",
    "CharacterCardExporter",
    "HermesSkill",
    "HermesSkillImporter",
    "Lorebook",
    "LorebookEntry",
    "LorebookExporter",
    "CharacterCardImporter",
    "LorebookImporter",
]