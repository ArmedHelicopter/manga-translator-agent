"""Project-scoped memory wiki layer for MGA.

Dual-structure memory system:
- Structured state (JSON) is the canonical source of truth
- Wiki projections (Markdown) are human-readable annotations

Single entry point: use get_memory_service(project_dir) for all operations.
"""

from __future__ import annotations

from pathlib import Path

from mga.memory.entities import (
    CharacterState,
    DecisionState,
    MemoryIndex,
    SceneState,
    TermState,
)
from mga.memory.state import StateManager
from mga.memory.sync import state_to_wiki, wiki_to_state
from mga.memory.wiki import WikiProjection

# Lazy imports for heavy modules
__all__ = [
    # Core entities (import directly for type hints)
    "CharacterState",
    "DecisionState",
    "MemoryIndex",
    "SceneState",
    "TermState",
    # State management
    "StateManager",
    "WikiProjection",
    "state_to_wiki",
    "wiki_to_state",
    # Service factory (primary interface)
    "get_memory_service",
    "reset_memory_service",
    # Lazy exports
    "LearnEngine",
    "MemoryRetrieval",
    "seed_memory_from_external_output",
    "build_and_save_profile",
    "load_all_profiles",
    "load_character_profile",
    "CharacterGraph",
    "GraphRetrieval",
    "EvolutionTracker",
]


def get_memory_service(project_dir: Path | str):
    """Get or create singleton MemoryService for project."""
    from .service import get_memory_service as _get
    return _get(project_dir)


def reset_memory_service(project_dir: Path | str):
    """Reset memory service for project (for testing)."""
    from .service import reset_memory_service as _reset
    return _reset(project_dir)


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
    if name in ("CharacterGraph",):
        from .graph import CharacterGraph
        return CharacterGraph
    if name in ("GraphRetrieval",):
        from .graph_retrieval import GraphRetrieval
        return GraphRetrieval
    if name in ("EvolutionTracker",):
        from .evolution_tracker import EvolutionTracker
        return EvolutionTracker
    if name in ("LearnEngine",):
        from .learn import LearnEngine
        return LearnEngine
    if name in ("MemoryRetrieval",):
        from .retrieval import MemoryRetrieval
        return MemoryRetrieval
    if name in ("seed_memory_from_external_output",):
        from .seeding import seed_memory_from_external_output
        return seed_memory_from_external_output
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")