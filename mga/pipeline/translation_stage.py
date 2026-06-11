"""Stage 4 -- Translation via LLM with context injection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .parsers import (
    parse_jsonish_response,
    parse_translation_response,
    parse_semantic_response,
    parse_persona_response,
    merge_footnotes,
    ensure_katakana_footnotes,
    normalize_name_translation,
    augment_footnotes_from_rationale,
    extract_structured_from_malformed,
)

from mga.cultural import CulturalAdapter
from mga.exceptions import StageExecutionError
from mga.memory import MemoryRetrieval
from mga.memory.character_memory_updater import CharacterMemoryUpdater
from mga.models import ProjectConfig, ProviderRoute, StageProviderConfig, TranslationCandidate
from mga.models.translation import (
    DialogueRealizationTrace,
    FootnoteEntry,
    PersonaRenderTrace,
    SemanticTranslation,
    TranslationProviderTrace,
)
from mga.providers import ProviderCascade

from .stages import PipelineContext, PipelineStage
from .prompts import (
    _build_translation_prompt,
    _build_semantic_translation_prompt,
    _build_persona_render_prompt,
    _format_scene_memory,
    _format_relationship_speech_rule,
    _relationship_speech_rule,
)


class TranslationStage(PipelineStage):
    """Translate each bubble using LLM with character and cultural context."""

    @property
    def name(self) -> str:
        return "translation"

    @property
    def order(self) -> int:
        return 40

    def execute(self, context: PipelineContext) -> PipelineContext:
        cfg: ProjectConfig = context.project_config
        provider_cascade = ProviderCascade(cfg, "translation")
        project_dir = Path(cfg.working_dir) if cfg.working_dir else Path(".")

        # Use optimized services if available in metadata
        memory_service = context.metadata.get("memory_service")
        cultural_service = context.metadata.get("cultural_service")

        # Initialize LLM cache for translation optimization
        llm_cache = context.llm_cache
        if llm_cache is None and cfg.llm_cache_enabled:
            from mga.cache import LLMCache
            cache_dir = cfg.llm_cache_dir or str(project_dir / ".mga_cache")
            llm_cache = LLMCache(cache_dir=cache_dir, enabled=True)
            context.llm_cache = llm_cache

        # Fallback to traditional services if not available
        if cultural_service is None:
            cultural_adapter = CulturalAdapter(project_dir)
        else:
            cultural_adapter = None  # Will use cultural_service directly
        memory_updater = CharacterMemoryUpdater(project_dir, memory_service=memory_service)
        name_glossary: dict[str, str] = {}
        context.memory_context.setdefault("character_profiles", {})
        context.memory_context.setdefault("page_profiles", {})
        character_memory_trace = context.artifacts.setdefault("character_memory", [])

        # Load character relationship graph if available
        graph_retrieval = None
        try:
            from mga.memory.graph import CharacterGraph
            from mga.memory.graph_retrieval import GraphRetrieval
            graph = CharacterGraph.load(Path(project_dir))
            if graph.graph.number_of_nodes() > 0:
                graph_retrieval = GraphRetrieval(graph)
        except Exception:
            pass

        all_translations: list[TranslationCandidate] = []
        realization_traces: list[DialogueRealizationTrace] = []
        for page_index, page in enumerate(context.pages):
            page_translations, page_traces = self._translate_page(
                provider_cascade, page, context, cfg, cultural_adapter,
                cultural_service=cultural_service,
                graph_retrieval=graph_retrieval, name_glossary=name_glossary,
                memory_updater=memory_updater,
                memory_trace=character_memory_trace,
                llm_cache=llm_cache,
            )
            all_translations.extend(page_translations)
            realization_traces.extend(page_traces)
            self._refresh_page_profiles_after_memory_update(
                context=context,
                memory_updater=memory_updater,
                next_page=context.pages[page_index + 1] if page_index + 1 < len(context.pages) else None,
            )

        context.translations = all_translations
        context.artifacts[self.name] = {
            "total_bubbles": len(all_translations),
            "name_glossary_entries": len(name_glossary),
            "dialogue_realization": {
                "version": "translation_graph_v0_a",
                "semantic_count": len(realization_traces),
                "persona_count": len(realization_traces),
                "entries": [trace.model_dump() for trace in realization_traces],
            },
            "provider_cascade_errors": provider_cascade.errors,
        }
        return context

    def _translate_page(
        self, provider_cascade: ProviderCascade, page: object,
        context: PipelineContext, cfg: ProjectConfig,
        cultural_adapter: CulturalAdapter | None,
        cultural_service: object | None = None,
        graph_retrieval: object | None = None,
        name_glossary: dict[str, str] | None = None,
        memory_updater: CharacterMemoryUpdater | None = None,
        memory_trace: list[dict[str, Any]] | None = None,
        llm_cache: object | None = None,
    ) -> tuple[list[TranslationCandidate], list[DialogueRealizationTrace]]:
        results: list[TranslationCandidate] = []
        traces: list[DialogueRealizationTrace] = []
        page_profiles = context.memory_context.get("page_profiles", {})
        mem_page = page_profiles.get(page.page_id, {})
        scene_contexts = context.memory_context.get("scene_contexts", {})
        scene_context = scene_contexts.get(page.page_id, {})
        cult_page = context.cultural_context.get(page.page_id, {})

        for bubble in page.bubbles:
            speaker = bubble.speaker_id or ""
            char_mem = mem_page.get(speaker, {})
            vision_ctx = self._build_vision_context(page, bubble)
            relationship_ctx, listener, relationship_data = self._build_relationship_context(
                page=page,
                bubble=bubble,
                speaker=speaker,
                graph_retrieval=graph_retrieval,
            )
            translation_memory = MemoryRetrieval.search_translation_memory(
                Path(cfg.working_dir) if cfg.working_dir else Path("."),
                bubble.source_text,
                limit=3,
            )

            semantic_prompt = _build_semantic_translation_prompt(
                bubble.source_text, cult_page, cfg.target_lang,
                vision_ctx=vision_ctx,
                translation_memory=translation_memory,
            )
            semantic, semantic_provider = self._call_semantic_llm(
                provider_cascade,
                bubble.bubble_id,
                semantic_prompt,
                source_text=bubble.source_text,
                target_lang=cfg.target_lang,
                llm_cache=llm_cache,
            )
            semantic.footnotes = ensure_katakana_footnotes(
                source_text=bubble.source_text,
                translated_text=semantic.text,
                footnotes=semantic.footnotes,
            )

            persona_prompt = _build_persona_render_prompt(
                bubble.source_text,
                semantic,
                char_mem,
                cfg.target_lang,
                relationship_ctx=relationship_ctx,
                vision_ctx=vision_ctx,
                listener_id=listener,
                scene_summary=getattr(page, "scene_summary", "") or "",
                scene_context=scene_context,
                relationship_data=relationship_data,
            )
            candidate, persona, persona_provider = self._call_persona_llm(
                provider_cascade=provider_cascade,
                bubble_id=bubble.bubble_id,
                prompt=persona_prompt,
                semantic=semantic,
                speaker_id=speaker or None,
                listener_id=listener,
                relationship_context_used=bool(relationship_ctx),
                memory_context_used=bool(char_mem or scene_context or translation_memory),
                vision_context_used=bool(vision_ctx),
                source_text=bubble.source_text,
                target_lang=cfg.target_lang,
                llm_cache=llm_cache,
            )

            # Apply cultural terminology substitutions
            cultural_processing_ctx = {
                "translation": candidate.text,
                "target_lang": cfg.target_lang,
            }
            if speaker and listener:
                cultural_processing_ctx.update({
                    "speaker": char_mem,
                    "listener": self._listener_memory_context(
                        listener=listener,
                        page_memory=mem_page,
                        global_memory=context.memory_context.get("character_profiles", {}),
                    ),
                    "relationship": self._cultural_relationship_context(
                        speaker=speaker,
                        listener=listener,
                        graph_retrieval=graph_retrieval,
                    ),
                })

            # Use optimized CulturalService if available
            if cultural_service is not None:
                processed = cultural_service.process_translation(
                    bubble.bubble_id, bubble.source_text,
                    {"translation": candidate.text, "target_lang": cfg.target_lang, **cultural_processing_ctx},
                )
            else:
                processed = cultural_adapter.process_translation(
                    bubble.bubble_id, bubble.source_text,
                    cultural_processing_ctx,
                )
            candidate.text = processed.get("translation", candidate.text)
            candidate.footnotes = merge_footnotes(semantic.footnotes, candidate.footnotes)
            candidate.footnotes = ensure_katakana_footnotes(
                source_text=bubble.source_text,
                translated_text=candidate.text,
                footnotes=candidate.footnotes,
            )
            candidate.text = normalize_name_translation(
                source_text=bubble.source_text,
                translated_text=candidate.text,
                glossary=name_glossary if name_glossary is not None else {},
            )
            requires_human_translation = self._requires_human_translation(candidate)
            if requires_human_translation:
                self._mark_human_translation_required(candidate, persona, bubble.source_text)
            persona.rendered_text = candidate.text
            results.append(candidate)
            # Build provider trace - can be None when cache hit
            semantic_trace = semantic_provider.trace("semantic_translation") if semantic_provider else {"operation": "semantic_translation", "provider": "", "model": ""}
            persona_trace = persona_provider.trace("persona_render") if persona_provider else {"operation": "persona_render", "provider": "", "model": ""}
            traces.append(DialogueRealizationTrace(
                page_id=page.page_id,
                bubble_id=bubble.bubble_id,
                source_text=bubble.source_text,
                speaker_id=speaker or None,
                provisional_speaker=getattr(bubble, "provisional_speaker", None),
                semantic=semantic,
                persona=persona,
                provider=TranslationProviderTrace(
                    semantic=semantic_trace,
                    persona=persona_trace,
                ),
                final_text=candidate.text,
            ))
            if speaker and memory_updater is not None and not requires_human_translation:
                update = memory_updater.update_from_translation(
                    speaker=speaker,
                    bubble=bubble,
                    page_id=page.page_id,
                    translated_text=candidate.text,
                    memory_before=char_mem,
                    prompt=persona_prompt,
                )
                context.memory_context["character_profiles"][speaker] = update.memory_after
                if memory_trace is not None:
                    memory_trace.append(update.trace_item)

        return results, traces

    def _requires_human_translation(self, candidate: TranslationCandidate) -> bool:
        return candidate.confidence < 0.5

    def _mark_human_translation_required(
        self,
        candidate: TranslationCandidate,
        persona: PersonaRenderTrace,
        source_text: str,
    ) -> None:
        candidate.text = source_text
        marker = "low confidence; human translation required"
        if candidate.rationale:
            candidate.rationale = f"{candidate.rationale}; {marker}"
        else:
            candidate.rationale = marker
        if "human_translation_required" not in persona.persona_moves:
            persona.persona_moves.append("human_translation_required")
        persona.rationale = candidate.rationale

    def _refresh_page_profiles_after_memory_update(
        self,
        *,
        context: PipelineContext,
        memory_updater: CharacterMemoryUpdater,
        next_page: object | None,
    ) -> None:
        if next_page is None:
            return
        page_profiles = context.memory_context.setdefault("page_profiles", {})
        next_profiles = dict(page_profiles.get(next_page.page_id, {}))
        for speaker, profile_dict in memory_updater.profiles_for_page(next_page).items():
            next_profiles[speaker] = profile_dict
            context.memory_context.setdefault("character_profiles", {})[speaker] = profile_dict
        page_profiles[next_page.page_id] = next_profiles

    def _build_vision_context(self, page: object, bubble: object) -> dict:
        ctx: dict[str, object] = {}
        if getattr(bubble, "provisional_speaker", None):
            ctx["provisional_speaker"] = bubble.provisional_speaker
        if getattr(bubble, "voice_hint", None):
            ctx["voice_hint"] = bubble.voice_hint
        if getattr(bubble, "box_type", None):
            ctx["box_type"] = bubble.box_type
        page_hints = getattr(page, "voice_hints", [])
        if page_hints:
            ctx["page_voice_hints"] = [str(h) for h in page_hints if str(h).strip()]
        return ctx

    def _build_relationship_context(
        self,
        *,
        page: object,
        bubble: object,
        speaker: str,
        graph_retrieval: object | None,
    ) -> tuple[str, str | None, dict | None]:
        """Build relationship context for translation prompt.

        Returns:
            - relationship_ctx: formatted string for prompt (e.g. "关系上下文：...")
            - listener: listener speaker_id or None
            - relationship_data: raw addressing dict from graph (for _format_relationship_speech_rule)
        """
        if not graph_retrieval or not speaker:
            return "", None, None
        listener = self._nearest_other_speaker(page, bubble, speaker)
        if not listener:
            return "", None, None
        relationship_ctx = graph_retrieval.get_translation_context(speaker, listener)
        relationship_data = graph_retrieval.get_addressing(speaker, listener)
        return relationship_ctx, listener, relationship_data

    def _nearest_other_speaker(
        self,
        page: object,
        bubble: object,
        speaker: str,
    ) -> str | None:
        bubbles = list(getattr(page, "bubbles", []))
        try:
            current_index = bubbles.index(bubble)
        except ValueError:
            current_index = 0
        current_order = self._bubble_order(bubble, current_index)

        candidates: list[tuple[int, int, int, str]] = []
        for index, other_bubble in enumerate(bubbles):
            other_speaker = getattr(other_bubble, "speaker_id", None)
            if not other_speaker or other_speaker == speaker:
                continue
            order = self._bubble_order(other_bubble, index)
            candidates.append((
                abs(order - current_order),
                abs(index - current_index),
                index,
                other_speaker,
            ))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][3]

    @staticmethod
    def _bubble_order(bubble: object, fallback: int) -> int:
        try:
            return int(getattr(bubble, "reading_order", fallback))
        except (TypeError, ValueError):
            return fallback

    def _listener_memory_context(
        self,
        *,
        listener: str,
        page_memory: dict,
        global_memory: dict,
    ) -> dict:
        listener_ctx = page_memory.get(listener)
        if isinstance(listener_ctx, dict):
            return listener_ctx
        global_ctx = global_memory.get(listener)
        if isinstance(global_ctx, dict):
            return global_ctx
        return {}

    def _cultural_relationship_context(
        self,
        *,
        speaker: str,
        listener: str,
        graph_retrieval: object | None,
    ) -> dict:
        if graph_retrieval is None or not hasattr(graph_retrieval, "get_addressing"):
            return {}
        try:
            addressing = graph_retrieval.get_addressing(speaker, listener)
        except Exception:
            return {}
        if not isinstance(addressing, dict):
            return {}

        formality = str(addressing.get("formality", ""))
        relationship = {
            "formality": formality,
            "honorific": str(addressing.get("honorific", "")),
            "relationship": str(addressing.get("relationship", "")),
        }
        relationship["distance"] = (
            "formal" if formality in {"polite", "formal", "honorific"} else "casual"
        )
        relationship["familiarity"] = {
            "intimate": "intimate",
            "casual": "close",
        }.get(formality, "acquaintance")
        return relationship

    def _call_semantic_llm(
        self,
        provider_cascade: ProviderCascade,
        bubble_id: str,
        prompt: str,
        source_text: str = "",
        target_lang: str = "",
        llm_cache: object | None = None,
    ) -> tuple[SemanticTranslation, object]:
        # Check cache first if available
        if llm_cache is not None and source_text and target_lang:
            cached = llm_cache.get(
                source_text=source_text,
                stage="semantic",
                target_lang=target_lang,
            )
            if cached is not None:
                return parse_semantic_response(bubble_id, cached), None

        messages = [{"role": "user", "content": prompt}]
        try:
            raw, candidate = provider_cascade.call_chat(
                messages,
                operation="semantic_translation",
                trace_context={"bubble_id": bubble_id},
            )
            # Cache the response if cache is available
            if llm_cache is not None and source_text:
                llm_cache.put(
                    source_text=source_text,
                    stage="semantic",
                    target_lang=target_lang,
                    response=raw,
                    provider=candidate.provider if candidate else "",
                    model=candidate.model if candidate else "",
                )
            return parse_semantic_response(bubble_id, raw), candidate
        except Exception as exc:
            raise StageExecutionError(
                f"Semantic translation provider failed for bubble '{bubble_id}': {exc}"
            ) from exc

    def _call_persona_llm(
        self,
        *,
        provider_cascade: ProviderCascade,
        bubble_id: str,
        prompt: str,
        semantic: SemanticTranslation,
        speaker_id: str | None,
        listener_id: str | None,
        relationship_context_used: bool,
        memory_context_used: bool,
        vision_context_used: bool,
        source_text: str = "",
        target_lang: str = "",
        llm_cache: object | None = None,
    ) -> tuple[TranslationCandidate, PersonaRenderTrace, object]:
        # Check cache first if available
        if llm_cache is not None and source_text and target_lang:
            cached = llm_cache.get(
                source_text=source_text,
                stage="persona",
                target_lang=target_lang,
            )
            if cached is not None:
                translation, trace = parse_persona_response(
                    bubble_id=bubble_id,
                    raw=cached,
                    semantic=semantic,
                    speaker_id=speaker_id,
                    listener_id=listener_id,
                    relationship_context_used=relationship_context_used,
                    memory_context_used=memory_context_used,
                    vision_context_used=vision_context_used,
                )
                return translation, trace, None

        messages = [{"role": "user", "content": prompt}]
        try:
            raw, candidate = provider_cascade.call_chat(
                messages,
                operation="persona_render",
                trace_context={"bubble_id": bubble_id},
            )
            # Cache the response if cache is available
            if llm_cache is not None and source_text:
                llm_cache.put(
                    source_text=source_text,
                    stage="persona",
                    target_lang=target_lang,
                    response=raw,
                    provider=candidate.provider if candidate else "",
                    model=candidate.model if candidate else "",
                )
            translation, trace = parse_persona_response(
                bubble_id=bubble_id,
                raw=raw,
                semantic=semantic,
                speaker_id=speaker_id,
                listener_id=listener_id,
                relationship_context_used=relationship_context_used,
                memory_context_used=memory_context_used,
                vision_context_used=vision_context_used,
            )
            return translation, trace, candidate
        except Exception as exc:
            raise StageExecutionError(
                f"Persona rendering provider failed for bubble '{bubble_id}': {exc}"
            ) from exc

