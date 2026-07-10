"""Incremental translation — load previous context, translate new chapter, update profiles."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .orchestrator import PipelineOrchestrator
from .stages import PipelineContext

logger = logging.getLogger(__name__)


class IncrementalTranslator:
    """Orchestrate incremental translation across chapters.

    Workflow:
    1. Load existing profiles (characters, terms, graph) from previous chapters
    2. Translate the new chapter using the orchestrator
    3. Update profiles with new observations from the translation
    4. Save updated profiles for future chapters
    """

    def __init__(self, project_dir: str | Path, config: Any = None) -> None:
        self.project_dir = Path(project_dir)
        self.config = config

    def translate_chapter(
        self,
        input_path: str | Path,
        output_path: str | Path,
        chapter_id: str = "",
    ) -> PipelineContext:
        """Translate a single chapter incrementally.

        1. Load previous context
        2. Run pipeline
        3. Update profiles
        4. Save state
        """
        logger.info("Starting incremental translation for chapter %s", chapter_id or input_path)

        # Step 1: Load previous context
        self._load_previous_context()
        logger.info("Loaded previous context: %d characters, %d terms",
                     self._count_characters(), self._count_terms())

        # Step 2: Run translation pipeline
        orchestrator = PipelineOrchestrator()
        context = orchestrator.run(str(input_path), str(output_path), self.config)

        # Step 3: Update profiles with new observations
        self._update_profiles(context, chapter_id)

        # Step 4: Save state
        self._save_state()

        logger.info("Incremental translation complete: %d translations, %d errors",
                     len(context.translations), len(context.errors))
        return context

    def _load_previous_context(self) -> None:
        """Load existing character profiles, terms, and graph."""
        # Profiles are already on disk — StateManager reads them directly
        # Graph loads from memory/state/character_graph.json
        pass  # StateManager and CharacterGraph load on demand

    def _update_profiles(self, context: PipelineContext, chapter_id: str) -> None:
        """Update character profiles with observations from this chapter."""
        if not context.translations:
            return

        from mga.memory.profile_builder import build_and_save_profile
        from mga.memory.evolution_tracker import EvolutionTracker

        tracker = EvolutionTracker(self.project_dir)

        # Build bubble lookup
        all_bubbles = {}
        for page in context.pages:
            for bubble in page.bubbles:
                all_bubbles[bubble.bubble_id] = bubble

        # Group translations by speaker
        speaker_translations: dict[str, list[tuple[str, str]]] = {}
        for candidate in context.translations:
            bubble = all_bubbles.get(candidate.bubble_id)
            if not bubble:
                continue
            speaker = bubble.speaker_id or bubble.speaker_name
            if not speaker:
                continue
            speaker_translations.setdefault(speaker, []).append(
                (bubble.source_text, candidate.text)
            )

        # Update each speaker's profile
        for speaker, pairs in speaker_translations.items():
            # Build profile from accumulated translations
            profile = build_and_save_profile(
                self.project_dir,
                character_id=speaker,
                name_jp=speaker,
            )

            # Detect speech pattern changes
            new_patterns = {}
            for src, tgt in pairs:
                # Simple pattern extraction: last char of source → last meaningful char of target
                if src and tgt:
                    import re
                    match = re.search(r"[ぁ-ん]{1,3}[。！？…]$", src)
                    if match:
                        jp_ending = match.group(0).rstrip("。！？…")
                        if jp_ending:
                            new_patterns[jp_ending] = tgt[-2:] if len(tgt) >= 2 else tgt

            if new_patterns:
                changes = tracker.detect_changes(
                    speaker, new_patterns, chapter=0, page=0,
                )
                if changes:
                    tracker.record_changes(changes)
                    tracker.update_profile(speaker, changes)

    def _save_state(self) -> None:
        """Save graph and any other state."""
        try:
            from mga.memory.graph import CharacterGraph
            graph = CharacterGraph.load(self.project_dir)
            graph.save(self.project_dir)
        except Exception as e:
            logger.warning("Failed to save graph: %s", e)

    def _count_characters(self) -> int:
        try:
            from mga.memory.state import StateManager
            return len(StateManager.list_characters(self.project_dir))
        except Exception:
            return 0

    def _count_terms(self) -> int:
        try:
            from mga.memory.state import StateManager
            return len(StateManager.list_terms(self.project_dir))
        except Exception:
            return 0


def incremental_translate(
    project_dir: str | Path,
    input_path: str | Path,
    output_path: str | Path,
    config: Any = None,
    chapter_id: str = "",
) -> PipelineContext:
    """Convenience function for incremental translation."""
    translator = IncrementalTranslator(project_dir, config)
    return translator.translate_chapter(input_path, output_path, chapter_id)
