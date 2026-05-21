"""Learning engine — orchestrate the 4-stage LLM-driven learning pipeline."""

from __future__ import annotations

import json
import logging
import tomli_w
from pathlib import Path
from typing import Any

from .aligner import align
from .dual_vision import analyze_pairs
from .models import LearningResult
from .pattern_extractor import extract_patterns
from .validator import validate

logger = logging.getLogger(__name__)


class LearningEngine:
    """Orchestrate L1-L4 learning pipeline to extract character profiles,
    terminology, style guides, and relationship graphs from existing translations.
    """

    def __init__(self, project_dir: str | Path, provider: Any = None) -> None:
        self.project_dir = Path(project_dir)
        self.provider = provider

    def learn(
        self,
        learn_dir: str | Path,
        mode: str = "auto",
    ) -> LearningResult:
        """Run the full L1-L4 pipeline.

        Args:
            learn_dir: Directory containing originals/ and translations/ subdirs.
            mode: 'manga', 'novel', or 'auto' (detect from file extensions).

        Returns:
            LearningResult with characters, terms, style_guide, character_graph.
        """
        # L1: Align
        logger.info("L1: Aligning page pairs from %s", learn_dir)
        pairs = align(self.project_dir, learn_dir)
        if not pairs:
            logger.warning("No page pairs found in %s", learn_dir)
            return LearningResult()
        logger.info("L1: Found %d page pairs", len(pairs))

        # L2: Vision / text analysis
        logger.info("L2: Analyzing %d page pairs with LLM", len(pairs))
        aligned = analyze_pairs(self.provider, pairs, mode=mode)
        logger.info("L2: Successfully analyzed %d/%d pairs", len(aligned), len(pairs))

        # L3: Pattern extraction
        logger.info("L3: Extracting patterns from %d aligned pages", len(aligned))
        result = extract_patterns(self.provider, aligned)
        logger.info("L3: Extracted %d characters, %d terms",
                     len(result.characters), len(result.terms))

        # L4: Validation
        logger.info("L4: Validating learning result")
        quality_report = validate(result)
        result.quality_report = quality_report
        logger.info("L4: Validation %s (%d issues)",
                     "passed" if quality_report["passed"] else "failed",
                     quality_report["total_issues"])

        # Write outputs
        self._write_outputs(result, quality_report)

        # Seed memory state
        self._seed_memory(result)

        return result

    def _write_outputs(self, result: LearningResult, quality_report: dict) -> None:
        """Write learning outputs to the project directory."""
        output_dir = self.project_dir / "memory" / "learned"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Write character profiles as JSON
        chars_dir = output_dir / "character_profiles"
        chars_dir.mkdir(exist_ok=True)
        for char in result.characters:
            char_id = char.get("character_id", "unknown")
            (chars_dir / f"{char_id}.json").write_text(
                json.dumps(char, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        # Write terminology as JSON
        terms_dir = output_dir / "terminology"
        terms_dir.mkdir(exist_ok=True)
        for term in result.terms:
            term_id = term.get("term_id", "unknown")
            (terms_dir / f"{term_id}.json").write_text(
                json.dumps(term, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        # Write style guide as TOML
        style_guide = result.style_guide.copy()
        style_guide.pop("raw_notes", None)  # Remove non-serializable notes
        (output_dir / "style_guide.toml").write_text(
            tomli_w.dumps(style_guide),
            encoding="utf-8",
        )

        # Write character graph as JSON
        (output_dir / "character_graph.json").write_text(
            json.dumps(result.character_graph, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        # Write quality report
        (output_dir / "quality_report.json").write_text(
            json.dumps(quality_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        # Write combined learning result
        (output_dir / "learning_result.json").write_text(
            json.dumps({
                "characters": result.characters,
                "terms": result.terms,
                "style_guide": result.style_guide,
                "character_graph": result.character_graph,
                "pages_processed": result.pages_processed,
            }, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        logger.info("Wrote learning outputs to %s", output_dir)

    def _seed_memory(self, result: LearningResult) -> None:
        """Seed memory state with learned character profiles and terminology."""
        try:
            from mga.memory.entities import CharacterState, TermState
            from mga.memory.state import StateManager
        except ImportError:
            logger.warning("Cannot seed memory: mga.memory not available")
            return

        for char_data in result.characters:
            char_state = CharacterState(
                character_id=char_data.get("character_id", ""),
                name_jp=char_data.get("name_jp", ""),
                name_zh=char_data.get("name_zh", ""),
                archetype=char_data.get("archetype", ""),
                speech_patterns=char_data.get("speech_patterns", {}),
                catchphrases=char_data.get("catchphrases", []),
                tone_spectrum=char_data.get("tone_spectrum", {}),
                translation_notes=char_data.get("translation_notes", {}),
            )
            StateManager.upsert_character(self.project_dir, char_state)

        for term_data in result.terms:
            term_state = TermState(
                term_id=term_data.get("term_id", ""),
                term_jp=term_data.get("term_jp", ""),
                term_zh=term_data.get("term_zh", ""),
                context=term_data.get("context", ""),
                cultural_weight=term_data.get("cultural_weight", ""),
                strategy=term_data.get("strategy", ""),
                frequency=term_data.get("frequency", 0),
            )
            StateManager.upsert_term(self.project_dir, term_state)

        logger.info("Seeded %d characters and %d terms into memory state",
                     len(result.characters), len(result.terms))
