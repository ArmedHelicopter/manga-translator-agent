"""Top-level package for the Manga Translate Agent host layer.

Architecture:
  Layer 0: Core (mga.core) — models, services, providers
  Layer 1: Infrastructure — config, formats
  Layer 2: Domain — memory, cultural, QA
  Layer 3: Orchestration — pipeline
  Layer 4: Interface — CLI

Quick start:
    from mga.core import create_provider, MemoryService, translate_bubble

    provider = create_provider("openai", {"api_key": "sk-..."})
    service = MemoryService("./my-project")
    result = translate_bubble(config, "こんにちは")
"""

from __future__ import annotations

from .core import (
    # Core models
    CharacterProfile,
    CharacterState,
    PipelineContext,
    ProjectConfig,
    TranslationCandidate,
    # Services
    TranslationService,
    MemoryService,
    CulturalService,
    ProviderCascade,
    # Convenience
    create_provider,
    get_provider,
    init_memory,
    translate_bubble,
)

__all__ = [
    "__version__",
    # Re-export core
    "CharacterProfile",
    "CharacterState",
    "PipelineContext",
    "ProjectConfig",
    "TranslationCandidate",
    "TranslationService",
    "MemoryService",
    "CulturalService",
    "ProviderCascade",
    "create_provider",
    "get_provider",
    "init_memory",
    "translate_bubble",
]

__version__ = "0.2.0"
