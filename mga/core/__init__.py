"""Core layer — zero-dependency models and unified services.

This module provides the foundational building blocks:
- Domain models (Pydantic schemas)
- Translation service (unified LLM interface)
- Provider factory (single entry for all providers)
- Memory service (character/scene/terminology management)
- Cultural service (adaptation and terminology)
- Prompt templates (token-optimized)
- Exception hierarchy

All other modules depend only on this layer.

Architecture:
  Layer 0: Core (this module)
  Layer 1: Infrastructure (config, providers, formats)
  Layer 2: Services (translation, memory, cultural, QA)
  Layer 3: Pipeline & CLI
"""

from __future__ import annotations

from .models import (
    CharacterProfile,
    CharacterState,
    PipelineContext,
    ProjectConfig,
    ProviderRoute,
    RunSummary,
    SceneContext,
    SceneState,
    StageProviderConfig,
    TermState,
    TranslationCandidate,
    TranslationMode,
    ProviderRole,
    TRANSLATION_SYSTEM_PROMPT,
    SEMANTIC_SYSTEM_PROMPT,
    PERSONA_SYSTEM_PROMPT,
    SIMPLE_JSON_SCHEMA,
)

from .services import (
    PromptBuilder,
    TranslationRequest,
    TranslationResponse,
    TranslationService,
    TranslationServiceResult,
    create_translation_service,
    translate_bubble,
)

from .provider_factory import (
    LLMProvider,
    BaseProvider,
    register_provider,
    create_provider,
    list_providers,
    get_provider,
    ProviderCascade,
)

from .memory_service import (
    StateManager,
    MemoryService,
    init_memory,
    sync_memory,
)

from .cultural_service import (
    ProblemType,
    Strategy,
    TermGrade,
    ProblemClassifier,
    StrategySelector,
    TerminologyManager,
    CulturalService,
    create_cultural_service,
    classify_text,
    select_strategy,
)

__all__ = [
    # Models
    "CharacterProfile",
    "CharacterState",
    "PipelineContext",
    "ProjectConfig",
    "ProviderRoute",
    "RunSummary",
    "SceneContext",
    "SceneState",
    "StageProviderConfig",
    "TermState",
    "TranslationCandidate",
    "TranslationMode",
    "ProviderRole",
    # Prompts
    "TRANSLATION_SYSTEM_PROMPT",
    "SEMANTIC_SYSTEM_PROMPT",
    "PERSONA_SYSTEM_PROMPT",
    "SIMPLE_JSON_SCHEMA",
    # Services
    "PromptBuilder",
    "TranslationRequest",
    "TranslationResponse",
    "TranslationService",
    "TranslationServiceResult",
    "create_translation_service",
    "translate_bubble",
    # Providers
    "LLMProvider",
    "BaseProvider",
    "register_provider",
    "create_provider",
    "list_providers",
    "get_provider",
    "ProviderCascade",
    # Memory
    "StateManager",
    "MemoryService",
    "init_memory",
    "sync_memory",
    # Cultural
    "ProblemType",
    "Strategy",
    "TermGrade",
    "ProblemClassifier",
    "StrategySelector",
    "TerminologyManager",
    "CulturalService",
    "create_cultural_service",
    "classify_text",
    "select_strategy",
]