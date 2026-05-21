"""Project-scoped memory wiki layer for MGA.

Dual-structure memory system:
- Structured state (JSON) is the canonical source of truth
- Wiki projections (Markdown) are human-readable annotations
"""

from __future__ import annotations

from mga.memory.entities import (
    CharacterState,
    DecisionState,
    MemoryIndex,
    SceneState,
    TermState,
)
from mga.memory.learn import LearnEngine
from mga.memory.retrieval import MemoryRetrieval
from mga.memory.seeding import seed_memory_from_external_output
from mga.memory.state import StateManager
from mga.memory.sync import state_to_wiki, wiki_to_state
from mga.memory.wiki import WikiProjection

__all__ = [
    "CharacterState",
    "DecisionState",
    "LearnEngine",
    "MemoryIndex",
    "MemoryRetrieval",
    "SceneState",
    "StateManager",
    "TermState",
    "WikiProjection",
    "build_and_save_profile",
    "load_all_profiles",
    "load_character_profile",
    "seed_memory_from_external_output",
    "state_to_wiki",
    "wiki_to_state",
]


def __getattr__(name: str):
    if name in ("load_character_profile", "load_all_profiles", "format_profile_for_prompt", "get_profile_as_dict"):
        from .profile_loader import load_character_profile, load_all_profiles, format_profile_for_prompt, get_profile_as_dict
        return {
            "load_character_profile": load_character_profile,
            "load_all_profiles": load_all_profiles,
            "format_profile_for_prompt": format_profile_for_prompt,
            "get_profile_as_dict": get_profile_as_dict,
        }[name]
    if name in ("build_and_save_profile", "build_profile_from_translations"):
        from .profile_builder import build_and_save_profile, build_profile_from_translations
        return {
            "build_and_save_profile": build_and_save_profile,
            "build_profile_from_translations": build_profile_from_translations,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
