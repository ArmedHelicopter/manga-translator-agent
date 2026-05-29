"""Stage 4 -- Translation via LLM with context injection."""

from __future__ import annotations

import json as _json
import re
from pathlib import Path
from typing import Any

from mga.cultural import CulturalAdapter
from mga.exceptions import StageExecutionError
from mga.memory.character_memory_updater import CharacterMemoryUpdater
from mga.models import ProjectConfig, TranslationCandidate
from mga.models.translation import (
    DialogueRealizationTrace,
    FootnoteEntry,
    PersonaRenderTrace,
    SemanticTranslation,
)
from mga.providers import get_provider

from .stages import PipelineContext, PipelineStage


def _build_translation_prompt(
    source_text: str,
    memory_ctx: dict,
    cultural_ctx: dict,
    target_lang: str,
    relationship_ctx: str = "",
    vision_ctx: dict | None = None,
) -> str:
    parts = [f"Translate the following manga dialogue to {target_lang}."]
    parts.append(
        "## 翻译规则\n"
        "- 所有文字必须翻译为中文，画面中不得出现日文（包括片假名）\n"
        "- 人名：直接按中文习惯翻译（可音译），不要写入 footnotes\n"
        "- 片假名外来语：翻译为对应中文词汇，并在 footnotes 中注明原文\n"
        "- 拟声词/拟态词：翻译为中文拟声词\n"
        "- 目标：读者只看到中文，不出现两种以上语言混杂"
    )
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
    if vision_ctx:
        parts.append("## Vision 补充提示")
        if vision_ctx.get("provisional_speaker"):
            parts.append(f"- 临时说话人：{vision_ctx['provisional_speaker']}（仅供语气参考，不是正式角色归属）")
        if vision_ctx.get("voice_hint"):
            parts.append(f"- 语言风格：{vision_ctx['voice_hint']}")
        if vision_ctx.get("box_type"):
            parts.append(f"- 文本框类型：{vision_ctx['box_type']}")
        if vision_ctx.get("page_voice_hints"):
            parts.append(f"- 页级语言观察：{'; '.join(vision_ctx['page_voice_hints'])}")
    if cultural_ctx.get("translation_context"):
        parts.append(cultural_ctx["translation_context"])
    parts.append(f"Source: {source_text}")
    parts.append(
        "Return a JSON object with keys:\n"
        "- 'text': the Chinese translation (no Japanese characters allowed)\n"
        "- 'footnotes': array of {\"original\": \"カタカナ原文\", \"translation\": \"中文翻译\", \"type\": \"loanword|sfx\"} for katakana loanwords/sfx only (empty array if none)\n"
        "- 'rationale': brief explanation of translation choices"
    )
    return "\n".join(parts)


def _build_semantic_translation_prompt(
    source_text: str,
    cultural_ctx: dict,
    target_lang: str,
    vision_ctx: dict | None = None,
) -> str:
    parts = [
        "## Semantic Translation",
        f"Translate the manga text to {target_lang} as a meaning-faithful semantic draft.",
        "## 语义层规则",
        "- 只负责原文意思、事实、术语、拟声词和脚注，不做人格化表演",
        "- 不使用角色档案、口癖、关系语气或临时说话人来改写声线",
        "- 所有文字必须翻译为中文，画面中不得出现日文（包括片假名）",
        "- 人名按中文习惯翻译或音译，不写入 footnotes",
        "- 片假名外来语和拟声词需翻译为中文，并在 footnotes 中注明原文",
    ]
    if vision_ctx and vision_ctx.get("box_type"):
        parts.append(f"- 文本框类型：{vision_ctx['box_type']}（只用于判断旁白/拟声词/招牌等文本功能）")
    if cultural_ctx.get("translation_context"):
        parts.append("## 文化与术语约束")
        parts.append(cultural_ctx["translation_context"])
    parts.append(f"Source: {source_text}")
    parts.append(
        "Return a JSON object with keys:\n"
        "- 'text': the meaning-faithful Chinese semantic draft\n"
        "- 'speech_act': brief label such as question, command, panic, narration, sfx, or statement\n"
        "- 'emotion': brief emotion label if inferable from the text itself\n"
        "- 'must_preserve': array of names, terms, or facts persona rendering must not change\n"
        "- 'footnotes': array of {\"original\": \"カタカナ原文\", \"translation\": \"中文翻译\", \"type\": \"loanword|sfx\"}\n"
        "- 'rationale': brief explanation of semantic choices\n"
        "- 'confidence': number from 0 to 1"
    )
    return "\n".join(parts)


def _build_persona_render_prompt(
    source_text: str,
    semantic: SemanticTranslation,
    memory_ctx: dict,
    target_lang: str,
    relationship_ctx: str = "",
    vision_ctx: dict | None = None,
    listener_id: str | None = None,
    scene_summary: str = "",
) -> str:
    parts = [
        "## Persona Rendering",
        "Render the semantic translation as final manga dialogue in Chinese.",
        "## 人格层规则",
        "- 只允许调整语气、句式、句尾、节奏、敬语层级和口癖",
        "- 不得改变事实、指代、事件逻辑、专名术语或 semantic must_preserve 内容",
        "- 最终文本必须适合直接嵌字，不要输出解释文字或脚注正文",
        f"Source: {source_text}",
        "## Semantic Translation",
        _json.dumps(semantic.model_dump(), ensure_ascii=False),
    ]
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
    if listener_id:
        parts.append(f"- listener_id: {listener_id}")
    if scene_summary:
        parts.append(f"## 场景摘要\n{scene_summary}")
    if vision_ctx:
        parts.append("## Vision 语气提示")
        if vision_ctx.get("provisional_speaker"):
            parts.append(f"- 临时说话人：{vision_ctx['provisional_speaker']}（只能作为弱语气提示，不是正式角色归属）")
        if vision_ctx.get("voice_hint"):
            parts.append(f"- 语言风格：{vision_ctx['voice_hint']}")
        if vision_ctx.get("page_voice_hints"):
            parts.append(f"- 页级语言观察：{'; '.join(vision_ctx['page_voice_hints'])}")
    parts.append(
        "Return a JSON object with keys:\n"
        "- 'text': final Chinese bubble text\n"
        "- 'persona_moves': array of short labels for voice changes you applied\n"
        "- 'rationale': brief explanation of persona rendering choices\n"
        "- 'confidence': number from 0 to 1"
    )
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
        project_dir = Path(cfg.working_dir) if cfg.working_dir else Path(".")
        cultural_adapter = CulturalAdapter(project_dir)
        memory_updater = CharacterMemoryUpdater(project_dir)
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
                provider, page, context, cfg, cultural_adapter, graph_retrieval, name_glossary,
                memory_updater=memory_updater,
                memory_trace=character_memory_trace,
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
        name_glossary: dict[str, str] | None = None,
        memory_updater: CharacterMemoryUpdater | None = None,
        memory_trace: list[dict[str, Any]] | None = None,
    ) -> tuple[list[TranslationCandidate], list[DialogueRealizationTrace]]:
        results: list[TranslationCandidate] = []
        traces: list[DialogueRealizationTrace] = []
        page_profiles = context.memory_context.get("page_profiles", {})
        mem_page = page_profiles.get(page.page_id, {})
        cult_page = context.cultural_context.get(page.page_id, {})

        for bubble in page.bubbles:
            speaker = bubble.speaker_id or ""
            char_mem = mem_page.get(speaker, {})
            vision_ctx = self._build_vision_context(page, bubble)
            relationship_ctx, listener = self._build_relationship_context(
                page=page,
                speaker=speaker,
                graph_retrieval=graph_retrieval,
            )

            semantic_prompt = _build_semantic_translation_prompt(
                bubble.source_text, cult_page, cfg.target_lang,
                vision_ctx=vision_ctx,
            )
            semantic = self._call_semantic_llm(provider, bubble.bubble_id, semantic_prompt)
            semantic.footnotes = self._ensure_katakana_footnotes(
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
            )
            candidate, persona = self._call_persona_llm(
                provider=provider,
                bubble_id=bubble.bubble_id,
                prompt=persona_prompt,
                semantic=semantic,
                speaker_id=speaker or None,
                listener_id=listener,
                relationship_context_used=bool(relationship_ctx),
                memory_context_used=bool(char_mem),
                vision_context_used=bool(vision_ctx),
            )

            # Apply cultural terminology substitutions
            processed = cultural_adapter.process_translation(
                bubble.bubble_id, bubble.source_text,
                {"translation": candidate.text, "target_lang": cfg.target_lang},
            )
            candidate.text = processed.get("translation", candidate.text)
            candidate.footnotes = self._merge_footnotes(semantic.footnotes, candidate.footnotes)
            candidate.footnotes = self._ensure_katakana_footnotes(
                source_text=bubble.source_text,
                translated_text=candidate.text,
                footnotes=candidate.footnotes,
            )
            candidate.text = self._normalize_name_translation(
                source_text=bubble.source_text,
                translated_text=candidate.text,
                glossary=name_glossary if name_glossary is not None else {},
            )
            persona.rendered_text = candidate.text
            results.append(candidate)
            traces.append(DialogueRealizationTrace(
                page_id=page.page_id,
                bubble_id=bubble.bubble_id,
                source_text=bubble.source_text,
                speaker_id=speaker or None,
                provisional_speaker=getattr(bubble, "provisional_speaker", None),
                semantic=semantic,
                persona=persona,
                final_text=candidate.text,
            ))
            if speaker and memory_updater is not None:
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
        speaker: str,
        graph_retrieval: object | None,
    ) -> tuple[str, str | None]:
        if not graph_retrieval or not speaker:
            return "", None
        other_speakers = [
            b.speaker_id
            for b in page.bubbles
            if b.speaker_id and b.speaker_id != speaker
        ]
        if not other_speakers:
            return "", None
        listener = other_speakers[0]
        return graph_retrieval.get_translation_context(speaker, listener), listener

    def _call_llm(self, provider: object, bubble_id: str, prompt: str) -> TranslationCandidate:
        messages = [{"role": "user", "content": prompt}]
        try:
            raw = provider.chat(messages)
            return self._parse_translation_response(bubble_id, raw)
        except Exception as exc:
            raise StageExecutionError(
                f"Translation provider failed for bubble '{bubble_id}': {exc}"
            ) from exc

    def _call_semantic_llm(self, provider: object, bubble_id: str, prompt: str) -> SemanticTranslation:
        messages = [{"role": "user", "content": prompt}]
        try:
            raw = provider.chat(messages)
            return self._parse_semantic_response(bubble_id, raw)
        except Exception as exc:
            raise StageExecutionError(
                f"Semantic translation provider failed for bubble '{bubble_id}': {exc}"
            ) from exc

    def _call_persona_llm(
        self,
        *,
        provider: object,
        bubble_id: str,
        prompt: str,
        semantic: SemanticTranslation,
        speaker_id: str | None,
        listener_id: str | None,
        relationship_context_used: bool,
        memory_context_used: bool,
        vision_context_used: bool,
    ) -> tuple[TranslationCandidate, PersonaRenderTrace]:
        messages = [{"role": "user", "content": prompt}]
        try:
            raw = provider.chat(messages)
            return self._parse_persona_response(
                bubble_id=bubble_id,
                raw=raw,
                semantic=semantic,
                speaker_id=speaker_id,
                listener_id=listener_id,
                relationship_context_used=relationship_context_used,
                memory_context_used=memory_context_used,
                vision_context_used=vision_context_used,
            )
        except Exception as exc:
            raise StageExecutionError(
                f"Persona rendering provider failed for bubble '{bubble_id}': {exc}"
            ) from exc

    def _parse_jsonish_response(self, raw: str) -> tuple[str, dict | None]:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1]).strip()

        parsed = None
        if text.startswith("{"):
            try:
                parsed = _json.loads(text)
            except ValueError:
                parsed = None
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed = _json.loads(text[start : end + 1])
                except ValueError:
                    parsed = None
        return text, parsed if isinstance(parsed, dict) else None

    def _parse_translation_response(self, bubble_id: str, raw: str) -> TranslationCandidate:
        """Parse LLM response — handles both plain text and JSON formats."""
        text, parsed = self._parse_jsonish_response(raw)

        if isinstance(parsed, dict):
            footnotes = [
                FootnoteEntry(**fn) for fn in parsed.get("footnotes", [])
                if isinstance(fn, dict)
            ]
            # Enforce policy: names are never footnotes.
            footnotes = [
                fn for fn in footnotes
                if fn.type in {"loanword", "sfx"}
            ]
            footnotes = self._augment_footnotes_from_rationale(
                text=parsed.get("text", parsed.get("translation", text)),
                rationale=parsed.get("rationale", ""),
                footnotes=footnotes,
            )
            return TranslationCandidate(
                bubble_id=bubble_id,
                text=parsed.get("text", parsed.get("translation", text)),
                rationale=parsed.get("rationale", ""),
                confidence=float(parsed.get("confidence", 0.8)),
                footnotes=footnotes,
            )

        fallback_text, fallback_footnotes = self._extract_structured_from_malformed(text)
        if fallback_text:
            return TranslationCandidate(
                bubble_id=bubble_id,
                text=fallback_text,
                rationale="",
                confidence=0.8,
                footnotes=[fn for fn in fallback_footnotes if fn.type in {"loanword", "sfx"}],
            )

        return TranslationCandidate(bubble_id=bubble_id, text=text)

    def _parse_semantic_response(self, bubble_id: str, raw: str) -> SemanticTranslation:
        text, parsed = self._parse_jsonish_response(raw)
        if isinstance(parsed, dict):
            footnotes = [
                FootnoteEntry(**fn) for fn in parsed.get("footnotes", [])
                if isinstance(fn, dict)
            ]
            footnotes = [fn for fn in footnotes if fn.type in {"loanword", "sfx"}]
            return SemanticTranslation(
                bubble_id=bubble_id,
                text=parsed.get("text", parsed.get("translation", text)),
                speech_act=parsed.get("speech_act"),
                emotion=parsed.get("emotion"),
                must_preserve=[str(item) for item in parsed.get("must_preserve", [])],
                footnotes=footnotes,
                rationale=parsed.get("rationale", ""),
                confidence=float(parsed.get("confidence", 0.8)),
            )

        fallback_text, fallback_footnotes = self._extract_structured_from_malformed(text)
        if fallback_text:
            return SemanticTranslation(
                bubble_id=bubble_id,
                text=fallback_text,
                confidence=0.8,
                footnotes=[fn for fn in fallback_footnotes if fn.type in {"loanword", "sfx"}],
            )
        return SemanticTranslation(bubble_id=bubble_id, text=text, confidence=0.8)

    def _parse_persona_response(
        self,
        *,
        bubble_id: str,
        raw: str,
        semantic: SemanticTranslation,
        speaker_id: str | None,
        listener_id: str | None,
        relationship_context_used: bool,
        memory_context_used: bool,
        vision_context_used: bool,
    ) -> tuple[TranslationCandidate, PersonaRenderTrace]:
        text, parsed = self._parse_jsonish_response(raw)
        rendered_text = text
        persona_moves: list[str] = []
        rationale = ""
        confidence = 0.8
        if isinstance(parsed, dict):
            rendered_text = parsed.get("text", parsed.get("translation", text))
            persona_moves = [str(item) for item in parsed.get("persona_moves", [])]
            rationale = parsed.get("rationale", "")
            confidence = float(parsed.get("confidence", 0.8))
        else:
            fallback_text, _ = self._extract_structured_from_malformed(text)
            if fallback_text:
                rendered_text = fallback_text

        candidate = TranslationCandidate(
            bubble_id=bubble_id,
            text=rendered_text,
            rationale=rationale,
            confidence=confidence,
            footnotes=list(semantic.footnotes),
        )
        trace = PersonaRenderTrace(
            bubble_id=bubble_id,
            speaker_id=speaker_id,
            listener_id=listener_id,
            semantic_text=semantic.text,
            rendered_text=rendered_text,
            persona_moves=persona_moves,
            relationship_context_used=relationship_context_used,
            memory_context_used=memory_context_used,
            vision_context_used=vision_context_used,
            rationale=rationale,
            confidence=confidence,
        )
        return candidate, trace

    _JP_HONORIFIC_PATTERN = re.compile(
        r"([ぁ-ゖァ-ヺー・]{1,12})(?:ちゃん|さん|くん|君|様)"
    )
    _ZH_NAME_SUFFIX_PATTERN = re.compile(r"([\u4e00-\u9fff]{1,6})(?:酱|醬)")

    def _normalize_name_translation(
        self,
        *,
        source_text: str,
        translated_text: str,
        glossary: dict[str, str],
    ) -> str:
        """Keep run-level name translation consistent for JP honorific mentions."""
        jp_matches = self._JP_HONORIFIC_PATTERN.findall(source_text or "")
        if not jp_matches:
            return translated_text

        key = jp_matches[0]
        current = translated_text or ""

        mapped_name = glossary.get(key)
        current_match = self._ZH_NAME_SUFFIX_PATTERN.search(current)
        current_name = current_match.group(1) if current_match else None

        if mapped_name is None and current_name:
            glossary[key] = current_name
            return current

        if mapped_name and current_name and mapped_name != current_name:
            return current.replace(current_name, mapped_name)

        return current

    _RATIONALE_TERM_RE = re.compile(r"[「『\"]([^「」『』\"]{1,20})[」』\"]")
    _KATAKANA_RE = re.compile(r"[ァ-ヺー]{2,}")
    _TEXT_FIELD_RE = re.compile(r'"text"\s*:\s*"((?:\\.|[^"\\])*)"', flags=re.DOTALL)
    _FOOTNOTE_ITEM_RE = re.compile(
        r'"original"\s*:\s*"((?:\\.|[^"\\])*)"\s*,\s*'
        r'"translation"\s*:\s*"((?:\\.|[^"\\])*)"\s*,\s*'
        r'"type"\s*:\s*"(loanword|sfx|name)"',
        flags=re.DOTALL,
    )

    def _augment_footnotes_from_rationale(
        self,
        *,
        text: str,
        rationale: str,
        footnotes: list[FootnoteEntry],
    ) -> list[FootnoteEntry]:
        """Recover footnotes when model wrote term mappings only in rationale."""
        existing_originals = {fn.original for fn in footnotes if fn.original}
        if not rationale:
            return footnotes

        candidates = self._RATIONALE_TERM_RE.findall(rationale)
        for term in candidates:
            if term in existing_originals:
                continue
            if not self._KATAKANA_RE.search(term):
                continue
            # If translated text appears to contain Chinese loanword replacement,
            # attach a conservative footnote entry.
            if text and len(text.strip()) > 0:
                footnotes.append(
                    FootnoteEntry(
                        original=term,
                        translation="见正文",
                        type="loanword",
                    )
                )
                existing_originals.add(term)
        return footnotes

    def _extract_structured_from_malformed(
        self, text: str
    ) -> tuple[str | None, list[FootnoteEntry]]:
        """Best-effort extractor for malformed JSON-like model outputs."""
        m_text = self._TEXT_FIELD_RE.search(text)
        extracted_text = None
        if m_text:
            extracted_text = self._unescape_json_string(m_text.group(1))

        extracted_footnotes: list[FootnoteEntry] = []
        for orig_raw, trans_raw, typ in self._FOOTNOTE_ITEM_RE.findall(text):
            original = self._unescape_json_string(orig_raw)
            translation = self._unescape_json_string(trans_raw)
            if original and translation:
                extracted_footnotes.append(
                    FootnoteEntry(original=original, translation=translation, type=typ)
                )
        return extracted_text, extracted_footnotes

    @staticmethod
    def _unescape_json_string(s: str) -> str:
        try:
            return _json.loads(f'"{s}"')
        except Exception:
            return s

    def _merge_footnotes(
        self,
        first: list[FootnoteEntry],
        second: list[FootnoteEntry],
    ) -> list[FootnoteEntry]:
        merged: list[FootnoteEntry] = []
        seen: set[tuple[str, str, str]] = set()
        for footnote in [*first, *second]:
            key = (footnote.original, footnote.translation, footnote.type)
            if key in seen:
                continue
            seen.add(key)
            merged.append(footnote)
        return merged

    def _ensure_katakana_footnotes(
        self,
        *,
        source_text: str,
        translated_text: str,
        footnotes: list[FootnoteEntry],
    ) -> list[FootnoteEntry]:
        """Enforce: katakana terms in source should have footnotes."""
        existing = {fn.original for fn in footnotes if fn.original}
        terms = self._KATAKANA_RE.findall(source_text or "")
        for term in terms:
            if term in existing:
                continue
            footnotes.append(
                FootnoteEntry(
                    original=term,
                    translation="见正文" if translated_text else "",
                    type="loanword",
                )
            )
            existing.add(term)
        return footnotes
