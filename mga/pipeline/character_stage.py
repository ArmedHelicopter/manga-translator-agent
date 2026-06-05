"""Stage 3 -- Character attribution and cultural context building."""

from __future__ import annotations

import re
from pathlib import Path

from mga.cultural import CulturalAdapter, load_fictional_script_context
from mga.memory import MemoryRetrieval
from mga.memory.seeding import seed_memory_from_external_output
from mga.memory.state import StateManager
from mga.models import ProjectConfig

from .stages import PipelineContext, PipelineStage


def _memory_state_empty(project_dir: Path) -> bool:
    """Return True if the memory/state/ directory has no entity files."""
    state_dir = project_dir / "memory" / "state"
    if not state_dir.exists():
        return True
    for subdir in ("characters", "scenes", "terms", "decisions"):
        entity_dir = state_dir / subdir
        if entity_dir.exists() and any(entity_dir.glob("*.json")):
            return False
    return True


def _external_output_exists(output_dir: Path) -> bool:
    """Return True if external output artifacts exist."""
    return (output_dir / "external-baseline-text-normalized.json").exists()


class CharacterAttributionStage(PipelineStage):
    """Retrieve character context and build cultural adaptation data per page."""

    @property
    def name(self) -> str:
        return "character"

    @property
    def order(self) -> int:
        return 30

    def execute(self, context: PipelineContext) -> PipelineContext:
        cfg: ProjectConfig = context.project_config
        project_dir = Path(cfg.working_dir) if cfg.working_dir else Path(".")

        # Auto-seed memory from external output on first runs
        if _memory_state_empty(project_dir):
            output_dir = Path(cfg.output_dir) if cfg.output_dir else project_dir / "output"
            if _external_output_exists(output_dir):
                seed_result = seed_memory_from_external_output(
                    str(project_dir), str(output_dir),
                )
                context.artifacts.setdefault(self.name, {})["auto_seed"] = seed_result

        cultural_adapter = CulturalAdapter(str(project_dir))
        all_memory: dict[str, dict] = {}
        all_cultural: dict[str, dict] = {}
        all_scene_contexts: dict[str, dict] = {}
        speaker_ids: set[str] = set()
        all_profiles: dict[str, dict] = {}  # global speaker → profile
        current_chapter = _current_chapter(context.metadata)

        for page in context.pages:
            page_mem = self._build_memory_context(
                project_dir,
                page,
                current_chapter=current_chapter,
            )
            page_cult = self._build_cultural_context(cultural_adapter, page)
            page_scene = self._build_scene_context(
                project_dir,
                page,
                current_chapter=current_chapter,
            )
            all_memory[page.page_id] = page_mem
            all_cultural[page.page_id] = page_cult
            if page_scene:
                all_scene_contexts[page.page_id] = page_scene
            # Accumulate global profiles for QA access
            all_profiles.update(page_mem)
            speaker_ids.update(page_mem.keys())

        context.memory_context = {
            "character_profiles": all_profiles,
            "page_profiles": all_memory,
            "scene_contexts": all_scene_contexts,
            "recent_translations": MemoryRetrieval.get_recent_translations(
                project_dir,
                speakers=sorted(speaker_ids),
            ),
            "profile_warnings": MemoryRetrieval.get_profile_warnings(
                project_dir,
                speakers=sorted(speaker_ids),
                current_chapter=current_chapter,
            ),
            "voice_evolutions": self._voice_evolution_context(all_profiles),
            "chapter_number": current_chapter or 0,
            "fictional_scripts": load_fictional_script_context(project_dir),
        }
        context.cultural_context = all_cultural
        context.artifacts[self.name] = {
            "pages_processed": len(context.pages),
        }
        return context

    def _build_memory_context(
        self,
        project_dir: Path,
        page: object,
        *,
        current_chapter: int | None = None,
    ) -> dict:
        ctx: dict = {}
        for bubble in page.bubbles:
            speaker = bubble.speaker_id
            if speaker and speaker not in ctx:
                char_ctx = MemoryRetrieval.get_character_context(
                    project_dir,
                    speaker,
                    chapter=current_chapter,
                )
                if char_ctx:
                    ctx[speaker] = char_ctx
        return ctx

    def _build_scene_context(
        self,
        project_dir: Path,
        page: object,
        *,
        current_chapter: int | None = None,
    ) -> dict:
        if current_chapter is None:
            return {}
        for page_number in _page_number_candidates(page):
            scene_ctx = MemoryRetrieval.get_scene_context(
                project_dir,
                current_chapter,
                page_number,
            )
            if scene_ctx:
                return scene_ctx
        return {}

    def _build_cultural_context(self, adapter: CulturalAdapter, page: object) -> dict:
        page_json = page.model_dump()
        return {
            "translation_context": adapter.get_translation_context(page_json),
            "analysis": adapter.analyze_page(page_json),
        }

    def _voice_evolution_context(self, profiles: dict[str, dict]) -> dict[str, list[dict]]:
        voice_evolutions: dict[str, list[dict]] = {}
        for speaker, profile in profiles.items():
            entries = profile.get("voice_evolutions")
            if isinstance(entries, list) and entries:
                voice_evolutions[speaker] = [
                    entry for entry in entries if isinstance(entry, dict)
                ]
        return voice_evolutions


def _current_chapter(metadata: dict) -> int | None:
    for key in ("chapter", "chapter_number", "chapter_id"):
        value = metadata.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            match = re.search(r"\d+", value)
            if match:
                return int(match.group(0))
    return None


def _page_number_candidates(page: object) -> list[int]:
    try:
        page_index = int(getattr(page, "page_index", 0))
    except (TypeError, ValueError):
        return []

    candidates: list[int] = []
    for candidate in (page_index + 1, page_index):
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates
