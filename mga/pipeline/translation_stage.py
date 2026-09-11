"""Stage 4 -- Translation via LLM with context injection."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .parallel_executor import ParallelExecutor, ParallelExecutionError
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
from .page_footnotes import get_page_footnote_service

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

    _RENDERABLE_VISION_BOX_TYPES = {"dialogue", "speech", "thought", "narration", "narrator"}
    _TRANSLATABLE_PAGE_TEXT_BOX_TYPES = {"cover_title", "chapter_title", "sign", "letter"}

    def __init__(self) -> None:
        self._logger = logging.getLogger(__name__)
        self._memory_lock = threading.Lock()

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

        # Determine translation parallelism from the stage config first, then
        # from CLI-level ProjectConfig fields for direct ProjectConfig callers.
        # Providers with low request limits can still opt into small batches.
        parallel_config = cfg.translation_config or {}
        parallel_mode = parallel_config.get("parallel_mode") or cfg.parallel_mode or "serial"

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
        used_parallel_mode = False

        # Check if semantic-parallel mode is enabled
        if parallel_mode == "semantic-parallel":
            try:
                all_translations, realization_traces = self._execute_semantic_parallel(
                    context=context,
                    provider_cascade=provider_cascade,
                    cfg=cfg,
                    cultural_adapter=cultural_adapter,
                    cultural_service=cultural_service,
                    graph_retrieval=graph_retrieval,
                    name_glossary=name_glossary,
                    memory_updater=memory_updater,
                    memory_trace=character_memory_trace,
                    llm_cache=llm_cache,
                    parallel_config=parallel_config,
                )
                used_parallel_mode = True
            except ParallelExecutionError as exc:
                self._logger.warning(
                    "Parallel execution failed (%s), falling back to serial mode", exc
                )
                # Clear any partial state
                context.translations = []
                context.memory_context["character_profiles"] = {}
                all_translations, realization_traces = self._execute_serial(
                    context=context,
                    provider_cascade=provider_cascade,
                    cfg=cfg,
                    cultural_adapter=cultural_adapter,
                    cultural_service=cultural_service,
                    graph_retrieval=graph_retrieval,
                    name_glossary=name_glossary,
                    memory_updater=memory_updater,
                    memory_trace=character_memory_trace,
                    llm_cache=llm_cache,
                )
                # Fallback to serial - don't mark parallel_mode in artifacts
        elif parallel_mode == "batch-parallel":
            try:
                all_translations, realization_traces = self._execute_batch_parallel(
                    context=context,
                    provider_cascade=provider_cascade,
                    cfg=cfg,
                    cultural_adapter=cultural_adapter,
                    cultural_service=cultural_service,
                    graph_retrieval=graph_retrieval,
                    name_glossary=name_glossary,
                    memory_updater=memory_updater,
                    memory_trace=character_memory_trace,
                    llm_cache=llm_cache,
                    parallel_config=parallel_config,
                )
                used_parallel_mode = True
            except ParallelExecutionError as exc:
                self._logger.warning(
                    "Batch-parallel execution failed (%s), falling back to serial mode", exc
                )
                # Clear any partial state
                context.translations = []
                context.memory_context["character_profiles"] = {}
                all_translations, realization_traces = self._execute_serial(
                    context=context,
                    provider_cascade=provider_cascade,
                    cfg=cfg,
                    cultural_adapter=cultural_adapter,
                    cultural_service=cultural_service,
                    graph_retrieval=graph_retrieval,
                    name_glossary=name_glossary,
                    memory_updater=memory_updater,
                    memory_trace=character_memory_trace,
                    llm_cache=llm_cache,
                )
        else:
            # Default serial execution
            all_translations, realization_traces = self._execute_serial(
                context=context,
                provider_cascade=provider_cascade,
                cfg=cfg,
                cultural_adapter=cultural_adapter,
                cultural_service=cultural_service,
                graph_retrieval=graph_retrieval,
                name_glossary=name_glossary,
                memory_updater=memory_updater,
                memory_trace=character_memory_trace,
                llm_cache=llm_cache,
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
        # Only record parallel_mode when parallel execution succeeded
        if used_parallel_mode:
            context.artifacts[self.name]["parallel_mode"] = parallel_mode
        return context

    def _execute_serial(
        self,
        context: PipelineContext,
        provider_cascade: ProviderCascade,
        cfg: ProjectConfig,
        cultural_adapter: CulturalAdapter | None,
        cultural_service: object | None,
        graph_retrieval: object | None,
        name_glossary: dict[str, str],
        memory_updater: CharacterMemoryUpdater,
        memory_trace: list[dict[str, Any]],
        llm_cache: object | None,
    ) -> tuple[list[TranslationCandidate], list[DialogueRealizationTrace]]:
        """Execute translation serially (original behavior)."""
        all_translations: list[TranslationCandidate] = []
        realization_traces: list[DialogueRealizationTrace] = []

        for page_index, page in enumerate(context.pages):
            page_translations, page_traces = self._translate_page(
                provider_cascade, page, context, cfg, cultural_adapter,
                cultural_service=cultural_service,
                graph_retrieval=graph_retrieval, name_glossary=name_glossary,
                memory_updater=memory_updater,
                memory_trace=memory_trace,
                llm_cache=llm_cache,
            )
            all_translations.extend(page_translations)
            realization_traces.extend(page_traces)
            self._refresh_page_profiles_after_memory_update(
                context=context,
                memory_updater=memory_updater,
                next_page=context.pages[page_index + 1] if page_index + 1 < len(context.pages) else None,
            )

        return all_translations, realization_traces

    def _execute_semantic_parallel(
        self,
        context: PipelineContext,
        provider_cascade: ProviderCascade,
        cfg: ProjectConfig,
        cultural_adapter: CulturalAdapter | None,
        cultural_service: object | None,
        graph_retrieval: object | None,
        name_glossary: dict[str, str],
        memory_updater: CharacterMemoryUpdater,
        memory_trace: list[dict[str, Any]],
        llm_cache: object | None,
        parallel_config: dict[str, Any],
    ) -> tuple[list[TranslationCandidate], list[DialogueRealizationTrace]]:
        """Execute translation with semantic-parallel bubble processing."""
        max_concurrent = parallel_config.get("max_concurrent_requests", cfg.translation_max_workers)
        semantic_timeout = parallel_config.get("semantic_timeout", 60)

        all_translations: list[TranslationCandidate] = []
        realization_traces: list[DialogueRealizationTrace] = []

        # Process pages serially to maintain memory consistency
        for page_index, page in enumerate(context.pages):
            page_translations, page_traces = self._translate_page_semantic_parallel(
                provider_cascade=provider_cascade,
                page=page,
                context=context,
                cfg=cfg,
                cultural_adapter=cultural_adapter,
                cultural_service=cultural_service,
                graph_retrieval=graph_retrieval,
                name_glossary=name_glossary,
                memory_updater=memory_updater,
                memory_trace=memory_trace,
                llm_cache=llm_cache,
                max_concurrent=max_concurrent,
                semantic_timeout=semantic_timeout,
            )
            all_translations.extend(page_translations)
            realization_traces.extend(page_traces)
            self._refresh_page_profiles_after_memory_update(
                context=context,
                memory_updater=memory_updater,
                next_page=context.pages[page_index + 1] if page_index + 1 < len(context.pages) else None,
            )

        return all_translations, realization_traces

    def _execute_batch_parallel(
        self,
        context: PipelineContext,
        provider_cascade: ProviderCascade,
        cfg: ProjectConfig,
        cultural_adapter: CulturalAdapter | None,
        cultural_service: object | None,
        graph_retrieval: object | None,
        name_glossary: dict[str, str],
        memory_updater: CharacterMemoryUpdater,
        memory_trace: list[dict[str, Any]],
        llm_cache: object | None,
        parallel_config: dict[str, Any],
    ) -> tuple[list[TranslationCandidate], list[DialogueRealizationTrace]]:
        """Execute translation with batch-parallel page processing."""
        batch_size = parallel_config.get("batch_size", cfg.pipeline_concurrency)
        max_concurrent = parallel_config.get("max_concurrent_requests", cfg.translation_max_workers)
        semantic_timeout = parallel_config.get("semantic_timeout", 60)

        all_translations: list[TranslationCandidate] = []
        realization_traces: list[DialogueRealizationTrace] = []

        # Split pages into batches
        pages = context.pages
        for batch_start in range(0, len(pages), batch_size):
            batch_pages = pages[batch_start:batch_start + batch_size]

            # Process pages in batch in parallel
            batch_results: list[tuple[int, list[TranslationCandidate], list[DialogueRealizationTrace]]] = []

            def translate_page_in_batch(page_idx: int, page: object) -> tuple[int, list[TranslationCandidate], list[DialogueRealizationTrace]]:
                page_translations, page_traces = self._translate_page_semantic_parallel(
                    provider_cascade=provider_cascade,
                    page=page,
                    context=context,
                    cfg=cfg,
                    cultural_adapter=cultural_adapter,
                    cultural_service=cultural_service,
                    graph_retrieval=graph_retrieval,
                    name_glossary=name_glossary,
                    memory_updater=memory_updater,
                    memory_trace=memory_trace,
                    llm_cache=llm_cache,
                    max_concurrent=max_concurrent,
                    semantic_timeout=semantic_timeout,
                )
                return page_idx, page_translations, page_traces

            with ThreadPoolExecutor(max_workers=len(batch_pages)) as executor:
                futures = {
                    executor.submit(translate_page_in_batch, batch_start + idx, page): idx
                    for idx, page in enumerate(batch_pages)
                }

                try:
                    for future in as_completed(futures, timeout=semantic_timeout * len(batch_pages)):
                        idx = futures[future]
                        try:
                            result = future.result()
                            batch_results.append(result)
                        except Exception as exc:
                            self._logger.error("Batch parallel translation failed for page index %s: %s", idx, exc)
                            raise ParallelExecutionError(
                                f"Page translation failed in batch: {exc}",
                                errors=[(idx, exc)],
                            )
                except TimeoutError:
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise ParallelExecutionError(
                        f"Batch parallel translation timeout after {semantic_timeout * len(batch_pages)}s",
                        errors=[],
                    )

            # Sort results by page_idx to maintain order
            batch_results.sort(key=lambda x: x[0])

            # Serial memory updates within batch (by page_id order)
            for page_idx, page_translations, page_traces in batch_results:
                all_translations.extend(page_translations)
                realization_traces.extend(page_traces)

                # Refresh profiles for next page
                next_page_idx = page_idx + 1
                if next_page_idx < len(pages):
                    self._refresh_page_profiles_after_memory_update(
                        context=context,
                        memory_updater=memory_updater,
                        next_page=pages[next_page_idx],
                    )

        return all_translations, realization_traces

    def _translate_page_semantic_parallel(
        self,
        provider_cascade: ProviderCascade,
        page: object,
        context: PipelineContext,
        cfg: ProjectConfig,
        cultural_adapter: CulturalAdapter | None,
        cultural_service: object | None,
        graph_retrieval: object | None,
        name_glossary: dict[str, str],
        memory_updater: CharacterMemoryUpdater,
        memory_trace: list[dict[str, Any]],
        llm_cache: object | None,
        max_concurrent: int = 3,
        semantic_timeout: float = 60,
    ) -> tuple[list[TranslationCandidate], list[DialogueRealizationTrace]]:
        """Translate a page with parallel semantic translation and serial persona rendering."""
        page_profiles = context.memory_context.get("page_profiles", {})
        mem_page = page_profiles.get(page.page_id, {})
        scene_contexts = context.memory_context.get("scene_contexts", {})
        scene_context = scene_contexts.get(page.page_id, {})
        cult_page = context.cultural_context.get(page.page_id, {})

        bubbles = self._translatable_bubbles(page)
        if not bubbles:
            return [], []

        # Step 1: Parallel semantic translation for all bubbles
        bubble_contexts = []
        for bubble in bubbles:
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

            bubble_contexts.append({
                "bubble": bubble,
                "speaker": speaker,
                "char_mem": char_mem,
                "vision_ctx": vision_ctx,
                "relationship_ctx": relationship_ctx,
                "listener": listener,
                "relationship_data": relationship_data,
                "semantic_prompt": semantic_prompt,
            })

        # Execute semantic translations in parallel
        semantic_results = self._parallel_semantic_translation(
            provider_cascade=provider_cascade,
            bubble_contexts=bubble_contexts,
            target_lang=cfg.target_lang,
            llm_cache=llm_cache,
            max_workers=max_concurrent,
            timeout=semantic_timeout,
        )

        # Step 2: Serial persona rendering (requires memory updates from previous bubbles)
        results: list[TranslationCandidate] = []
        traces: list[DialogueRealizationTrace] = []

        for idx, bubble_ctx in enumerate(bubble_contexts):
            bubble = bubble_ctx["bubble"]
            speaker = bubble_ctx["speaker"]
            char_mem = bubble_ctx["char_mem"]
            vision_ctx = bubble_ctx["vision_ctx"]
            relationship_ctx = bubble_ctx["relationship_ctx"]
            listener = bubble_ctx["listener"]
            relationship_data = bubble_ctx["relationship_data"]

            semantic = semantic_results[idx]

            # Apply katakana footnotes to semantic result
            semantic.footnotes = ensure_katakana_footnotes(
                source_text=bubble.source_text,
                translated_text=semantic.text,
                footnotes=semantic.footnotes,
            )

            # Get updated character memory (may have been updated by previous bubbles on same page)
            mem_page_current = context.memory_context.get("page_profiles", {}).get(page.page_id, {})
            char_mem_updated = mem_page_current.get(speaker, char_mem)

            persona_prompt = _build_persona_render_prompt(
                bubble.source_text,
                semantic,
                char_mem_updated,
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
                memory_context_used=bool(char_mem_updated or scene_context or MemoryRetrieval.search_translation_memory(
                    Path(cfg.working_dir) if cfg.working_dir else Path("."),
                    bubble.source_text,
                    limit=3,
                )),
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
                    "speaker": char_mem_updated,
                    "listener": self._listener_memory_context(
                        listener=listener,
                        page_memory=mem_page_current,
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
                glossary=name_glossary,
            )
            requires_human_translation = self._requires_human_translation(candidate)
            if requires_human_translation:
                self._mark_human_translation_required(candidate, persona, bubble.source_text)
            persona.rendered_text = candidate.text
            results.append(candidate)

            # Build provider trace
            semantic_trace = {"operation": "semantic_translation", "provider": "", "model": ""}
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

            # Update memory after persona rendering
            if speaker and memory_updater is not None and not requires_human_translation:
                update = memory_updater.update_from_translation(
                    speaker=speaker,
                    bubble=bubble,
                    page_id=page.page_id,
                    translated_text=candidate.text,
                    memory_before=char_mem_updated,
                    prompt=persona_prompt,
                )
                with self._memory_lock:
                    context.memory_context["character_profiles"][speaker] = update.memory_after
                    # Update page profile for next bubble on same page
                    page_profiles = context.memory_context.setdefault("page_profiles", {})
                    if page.page_id not in page_profiles:
                        page_profiles[page.page_id] = {}
                    page_profiles[page.page_id][speaker] = update.memory_after
                if memory_trace is not None:
                    memory_trace.append(update.trace_item)

        # Compile page-level footnotes after all bubbles are translated
        self._compile_page_footnotes(page, results, context)

        return results, traces

    def _parallel_semantic_translation(
        self,
        provider_cascade: ProviderCascade,
        bubble_contexts: list[dict[str, Any]],
        target_lang: str,
        llm_cache: object | None,
        max_workers: int = 3,
        timeout: float = 60,
    ) -> list[SemanticTranslation]:
        """Execute semantic translations in parallel using ThreadPoolExecutor."""
        results: list[SemanticTranslation | Exception] = [None] * len(bubble_contexts)

        def translate_single(idx: int, ctx: dict[str, Any]) -> tuple[int, SemanticTranslation]:
            bubble = ctx["bubble"]
            semantic_prompt = ctx["semantic_prompt"]

            semantic, _ = self._call_semantic_llm(
                provider_cascade,
                bubble.bubble_id,
                semantic_prompt,
                source_text=bubble.source_text,
                target_lang=target_lang,
                llm_cache=llm_cache,
            )
            return idx, semantic

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(translate_single, idx, ctx): idx
                for idx, ctx in enumerate(bubble_contexts)
            }

            try:
                for future in as_completed(futures, timeout=timeout):
                    idx = futures[future]
                    try:
                        result_idx, semantic = future.result()
                        results[result_idx] = semantic
                    except Exception as exc:
                        self._logger.error("Parallel semantic translation failed for index %s: %s", idx, exc)
                        results[idx] = exc
            except TimeoutError:
                executor.shutdown(wait=False, cancel_futures=True)
                raise ParallelExecutionError(
                    f"Parallel semantic translation timeout after {timeout}s",
                    errors=[],
                )

        # Check for errors and convert to final list
        final_results: list[SemanticTranslation] = []
        errors: list[tuple[int, Exception]] = []
        for idx, result in enumerate(results):
            if isinstance(result, Exception):
                errors.append((idx, result))
            else:
                final_results.append(result)

        if errors:
            raise ParallelExecutionError(
                f"{len(errors)} semantic translations failed out of {len(bubble_contexts)}",
                errors=errors,
            )

        # Return in original order
        return [r for r in results if r is not None]

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

        for bubble in self._translatable_bubbles(page):
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

        # Compile page-level footnotes after all bubbles are translated
        self._compile_page_footnotes(page, results, context)

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

    def _compile_page_footnotes(
        self,
        page: object,
        translations: list[TranslationCandidate],
        context: PipelineContext,
    ) -> None:
        """Compile page-level footnotes from bubble translations.

        Aggregates all footnotes from bubble translations into a unified
        page-level footnote section, deduplicating and ordering them.
        """
        from mga.pipeline.page_footnotes import get_page_footnote_service

        bubbles = list(getattr(page, "bubbles", []))
        if not bubbles or not translations:
            return

        # Get page context for better explanations
        page_context = getattr(page, "scene_summary", "") or ""

        # Compile page footnotes
        footnote_service = get_page_footnote_service()
        page_footnotes = footnote_service.compile_page_footnotes(
            bubbles=bubbles,
            translations=translations,
            page_context=page_context,
        )

        # Store on page object
        if hasattr(page, "page_footnotes"):
            page.page_footnotes = page_footnotes

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

    @classmethod
    def _translatable_bubbles(cls, page: object) -> list[object]:
        bubbles = list(getattr(page, "bubbles", []) or [])
        page_is_contents = any(
            "contents" in str(getattr(bubble, "source_text", "") or "").lower()
            for bubble in bubbles
        )
        return [
            bubble
            for bubble in bubbles
            if cls._is_translatable_bubble(bubble, page_is_contents=page_is_contents)
        ]

    @classmethod
    def _is_translatable_bubble(cls, bubble: object, *, page_is_contents: bool = False) -> bool:
        if not (
            str(getattr(bubble, "bubble_id", "") or "").startswith("vision-")
            or getattr(bubble, "detection_source", None) == "vision"
        ):
            return True
        box_type = str(getattr(bubble, "box_type", "") or "dialogue").strip().lower()
        if not box_type:
            return True
        source_text = str(getattr(bubble, "source_text", "") or "").strip()
        if source_text and len(source_text) <= 4 and source_text.isascii() and source_text.replace(" ", "").isalpha():
            return False
        if page_is_contents and box_type not in {"sfx", "graffiti"}:
            return True
        if box_type in cls._TRANSLATABLE_PAGE_TEXT_BOX_TYPES:
            return True
        # Vision reports all visible text, including SFX, page numbers, signs,
        # and chapter labels. Translating those as dialogue recreates the
        # page-009 regression: Chinese SFX/page-number text is rendered onto art
        # instead of staying as a footnote or non-dialogue page element.
        return box_type in cls._RENDERABLE_VISION_BOX_TYPES

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

