"""Stage 4 -- Translation via LLM with context injection."""

from __future__ import annotations

from typing import Any

from mga.cultural import CulturalAdapter
from mga.models import ProjectConfig, TranslationCandidate
from mga.providers import get_provider

from .stages import PipelineContext, PipelineStage


def _build_translation_prompt(
    source_text: str,
    memory_ctx: dict,
    cultural_ctx: dict,
    target_lang: str,
    relationship_ctx: str = "",
) -> str:
    parts = [f"Translate the following manga dialogue to {target_lang}."]
    if memory_ctx:
        parts.append("## 角色档案")
        if memory_ctx.get("name_jp") or memory_ctx.get("name_zh"):
            name_line = f"- 名字：{memory_ctx.get('name_jp', '')}"
            if memory_ctx.get("name_zh"):
                name_line += f" → {memory_ctx['name_zh']}"
            parts.append(name_line)
        if memory_ctx.get("archetype"):
            parts.append(f"- 原型：{memory_ctx['archetype']}")
        if memory_ctx.get("speech_patterns"):
            patterns = "; ".join(f"{k}={v}" for k, v in memory_ctx["speech_patterns"].items())
            parts.append(f"- 语言模式：{patterns}")
        if memory_ctx.get("catchphrases"):
            parts.append(f"- 口头禅：{', '.join(memory_ctx['catchphrases'])}")
        if memory_ctx.get("tone_spectrum"):
            tones = "; ".join(f"{k}={v}" for k, v in memory_ctx["tone_spectrum"].items())
            parts.append(f"- 语气：{tones}")
        if memory_ctx.get("translation_notes"):
            notes = "; ".join(f"{k}={v}" for k, v in memory_ctx["translation_notes"].items())
            parts.append(f"- 翻译注意：{notes}")
    if relationship_ctx:
        parts.append(relationship_ctx)
    if cultural_ctx.get("translation_context"):
        parts.append(cultural_ctx["translation_context"])
    parts.append(f"Source: {source_text}")
    parts.append("Return a JSON object with 'text' and 'rationale' keys.")
    return "\n".join(parts)


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
        provider = self._get_provider(cfg)
        project_dir = cfg.working_dir or "."
        cultural_adapter = CulturalAdapter(project_dir)

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
        for page in context.pages:
            page_translations = self._translate_page(
                provider, page, context, cfg, cultural_adapter, graph_retrieval,
            )
            all_translations.extend(page_translations)

        context.translations = all_translations
        context.artifacts[self.name] = {
            "total_bubbles": len(all_translations),
        }
        return context

    def _get_provider(self, cfg: ProjectConfig) -> object:
        route = cfg.provider_routes.get("translation")
        if route and route.primary.provider:
            name = route.primary.provider
            settings = cfg.provider_settings.get(name, {})
            if route.primary.model and "model" not in settings:
                settings["model"] = route.primary.model
            return get_provider(name, **settings)
        settings = cfg.provider_settings.get("openai", {})
        return get_provider("openai", **settings)

    def _translate_page(
        self, provider: object, page: object,
        context: PipelineContext, cfg: ProjectConfig,
        cultural_adapter: CulturalAdapter,
        graph_retrieval: object | None = None,
    ) -> list[TranslationCandidate]:
        results: list[TranslationCandidate] = []
        page_profiles = context.memory_context.get("page_profiles", {})
        mem_page = page_profiles.get(page.page_id, {})
        cult_page = context.cultural_context.get(page.page_id, {})

        for bubble in page.bubbles:
            speaker = bubble.speaker_id or bubble.speaker_name or ""
            char_mem = mem_page.get(speaker, {})

            # Get relationship context from graph
            relationship_ctx = ""
            if graph_retrieval and speaker:
                # Find the most likely listener on this page
                other_speakers = [
                    b.speaker_id or b.speaker_name
                    for b in page.bubbles
                    if (b.speaker_id or b.speaker_name) and (b.speaker_id or b.speaker_name) != speaker
                ]
                if other_speakers:
                    # Use the first other speaker as the listener
                    listener = other_speakers[0]
                    relationship_ctx = graph_retrieval.get_translation_context(speaker, listener)

            prompt = _build_translation_prompt(
                bubble.source_text, char_mem, cult_page, cfg.target_lang,
                relationship_ctx=relationship_ctx,
            )
            candidate = self._call_llm(provider, bubble.bubble_id, prompt)

            # Apply cultural terminology substitutions
            processed = cultural_adapter.process_translation(
                bubble.bubble_id, bubble.source_text,
                {"translation": candidate.text, "target_lang": cfg.target_lang},
            )
            candidate.text = processed.get("translation", candidate.text)
            results.append(candidate)

        return results

    def _call_llm(self, provider: object, bubble_id: str, prompt: str) -> TranslationCandidate:
        messages = [{"role": "user", "content": prompt}]
        try:
            raw = provider.chat(messages)
            return self._parse_translation_response(bubble_id, raw)
        except Exception as exc:
            return TranslationCandidate(
                bubble_id=bubble_id, text="", rationale=f"LLM error: {exc}",
            )

    def _parse_translation_response(self, bubble_id: str, raw: str) -> TranslationCandidate:
        """Parse LLM response — handles both plain text and JSON formats."""
        import json as _json
        text = raw.strip()
        # Try JSON parse (LLM may return {"text": "...", "rationale": "..."})
        if text.startswith("{"):
            try:
                data = _json.loads(text)
                return TranslationCandidate(
                    bubble_id=bubble_id,
                    text=data.get("text", data.get("translation", text)),
                    rationale=data.get("rationale", ""),
                    confidence=float(data.get("confidence", 0.8)),
                )
            except (ValueError, KeyError):
                pass
        return TranslationCandidate(bubble_id=bubble_id, text=text)
