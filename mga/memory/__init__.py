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
from mga.memory.retrieval import MemoryRetrieval
from mga.memory.state import StateManager
from mga.memory.sync import state_to_wiki, wiki_to_state
from mga.memory.wiki import WikiProjection

__all__ = [
    "CharacterState",
    "DecisionState",
    "MemoryIndex",
    "MemoryRetrieval",
    "SceneState",
    "StateManager",
    "TermState",
    "WikiProjection",
    "state_to_wiki",
    "wiki_to_state",
]
