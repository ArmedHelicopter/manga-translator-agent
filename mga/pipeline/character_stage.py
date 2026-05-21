"""Stage 3 -- Character attribution and cultural context building."""

from __future__ import annotations

from pathlib import Path

from mga.cultural import CulturalAdapter
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

        for page in context.pages:
            page_mem = self._build_memory_context(project_dir, page)
            page_cult = self._build_cultural_context(cultural_adapter, page)
            all_memory[page.page_id] = page_mem
            all_cultural[page.page_id] = page_cult

        context.memory_context = all_memory
        context.cultural_context = all_cultural
        context.artifacts[self.name] = {
            "pages_processed": len(context.pages),
        }
        return context

    def _build_memory_context(self, project_dir: Path, page: object) -> dict:
        ctx: dict = {}
        for bubble in page.bubbles:
            speaker = bubble.speaker_id or bubble.speaker_name
            if speaker and speaker not in ctx:
                char_ctx = MemoryRetrieval.get_character_context(project_dir, speaker)
                if char_ctx:
                    ctx[speaker] = char_ctx
        return ctx

    def _build_cultural_context(self, adapter: CulturalAdapter, page: object) -> dict:
        page_json = page.model_dump()
        return {
            "translation_context": adapter.get_translation_context(page_json),
            "analysis": adapter.analyze_page(page_json),
        }
