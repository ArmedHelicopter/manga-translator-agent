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
        character_graph_json = json.dumps(result.character_graph, ensure_ascii=False, indent=2) + "\n"
        (output_dir / "character_graph.json").write_text(
            character_graph_json,
            encoding="utf-8",
        )

        # Write product-facing memory/config artifacts consumed by the main pipeline.
        (self.project_dir / "style_guide.toml").write_text(
            tomli_w.dumps(style_guide),
            encoding="utf-8",
        )
        (self.project_dir / "character_graph.json").write_text(
            character_graph_json,
            encoding="utf-8",
        )
        self._write_character_profiles_toml(result)
        self._write_terminology_toml(result)
        self._write_character_graph_state(result)

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

    def _write_character_profiles_toml(self, result: LearningResult) -> None:
        profiles_dir = self.project_dir / "character_profiles"
        profiles_dir.mkdir(parents=True, exist_ok=True)
        for char in result.characters:
            char_id = str(char.get("character_id") or "unknown")
            provenance = char.get("provenance", {})
            if not isinstance(provenance, dict):
                provenance = {}
            if "confidence" not in provenance and char.get("confidence") is not None:
                provenance["confidence"] = char["confidence"]
            provenance = {"source": "learning_engine", **provenance}
            payload = {
                "meta": {
                    "character_id": char_id,
                    "name_jp": str(char.get("name_jp", "")),
                    "name_zh": str(char.get("name_zh", "")),
                    "archetype": str(char.get("archetype", "")),
                    "provenance": provenance,
                },
                "speech_patterns": self._stringify_mapping(char.get("speech_patterns", {})),
                "catchphrases": {
                    "patterns": [str(item) for item in char.get("catchphrases", [])],
                },
                "tone_spectrum": self._stringify_mapping(char.get("tone_spectrum", {})),
                "translation_notes": self._stringify_mapping(
                    char.get("translation_notes", {})
                ),
            }
            relationship_speech = self._relationship_speech(char.get("relationship_speech", {}))
            if relationship_speech:
                payload["relationship_speech"] = relationship_speech
            voice_evolution = char.get("voice_evolution", char.get("voice_evolutions", []))
            if isinstance(voice_evolution, list) and voice_evolution:
                payload["voice_evolution"] = voice_evolution
            (profiles_dir / f"{char_id}.toml").write_text(
                tomli_w.dumps(payload),
                encoding="utf-8",
            )

    def _stringify_mapping(self, raw: object) -> dict[str, str]:
        if not isinstance(raw, dict):
            return {}
        result: dict[str, str] = {}
        for key, value in raw.items():
            if isinstance(value, list):
                result[str(key)] = ", ".join(str(item) for item in value)
            else:
                result[str(key)] = str(value)
        return result

    def _relationship_speech(self, raw: object) -> dict[str, dict[str, Any]]:
        if not isinstance(raw, dict):
            return {}
        result: dict[str, dict[str, Any]] = {}
        for listener, value in raw.items():
            if not isinstance(value, dict):
                continue
            result[str(listener)] = {
                str(key): [str(part) for part in item] if isinstance(item, list) else str(item)
                for key, item in value.items()
            }
        return result

    def _write_terminology_toml(self, result: LearningResult) -> None:
        term_dir = self.project_dir / "terminology"
        term_dir.mkdir(parents=True, exist_ok=True)
        payload = {"terms": {}}
        for term in result.terms:
            key = term.get("term_jp") or term.get("term_id") or "unknown"
            term_payload = {
                "term_jp": term.get("term_jp", key),
                "term_target": term.get("term_zh", ""),
                "strategy": term.get("strategy", ""),
                "notes": term.get("context", ""),
                "confirmed": False,
                "pending_human_review": True,
            }
            if term.get("candidate_translations"):
                term_payload["candidate_translations"] = [
                    str(item) for item in term.get("candidate_translations", [])
                ]
            if term.get("accepted_reason"):
                term_payload["accepted_reason"] = str(term["accepted_reason"])
            if isinstance(term.get("rejected_reasons"), dict) and term["rejected_reasons"]:
                term_payload["rejected_reasons"] = {
                    str(candidate): str(reason)
                    for candidate, reason in term["rejected_reasons"].items()
                }
            if term.get("applicability_scope"):
                term_payload["applicability_scope"] = str(term["applicability_scope"])
            payload["terms"][key] = term_payload
        (term_dir / "learned.toml").write_text(
            tomli_w.dumps(payload),
            encoding="utf-8",
        )

    def _write_character_graph_state(self, result: LearningResult) -> None:
        try:
            from mga.memory.graph import CharacterGraph
        except ImportError:
            return

        graph_data = result.character_graph or {"nodes": [], "edges": []}
        graph = CharacterGraph()
        for node in graph_data.get("nodes", []):
            node_id = node.get("id") or node.get("character_id") or node.get("label")
            if node_id:
                graph.add_character(str(node_id), **{k: v for k, v in node.items() if k != "id"})
        for edge in graph_data.get("edges", []):
            source = edge.get("source")
            target = edge.get("target")
            if not source or not target:
                continue
            attrs = {
                k: v
                for k, v in edge.items()
                if k not in {"source", "target", "relationship", "formality", "honorific", "notes"}
            }
            graph.add_relationship(
                str(source),
                str(target),
                relationship=edge.get("relationship", ""),
                formality=edge.get("formality", "casual") or "casual",
                honorific=edge.get("honorific", ""),
                notes=edge.get("notes", ""),
                **attrs,
            )
        graph.save(self.project_dir)

    def _seed_memory(self, result: LearningResult) -> None:
        """Seed memory state with learned character profiles and terminology."""
        try:
            from mga.memory.entities import CharacterState, TermState
            from mga.memory.state import StateManager
        except ImportError:
            logger.warning("Cannot seed memory: mga.memory not available")
            return

        for char_data in result.characters:
            provenance = char_data.get("provenance", {})
            if not isinstance(provenance, dict):
                provenance = {}
            if "confidence" not in provenance and char_data.get("confidence") is not None:
                provenance["confidence"] = char_data["confidence"]
            provenance = {"source": "learning_engine", **provenance}
            char_state = CharacterState(
                character_id=char_data.get("character_id", ""),
                name_jp=char_data.get("name_jp", ""),
                name_zh=char_data.get("name_zh", ""),
                archetype=char_data.get("archetype", ""),
                speech_patterns=char_data.get("speech_patterns", {}),
                catchphrases=char_data.get("catchphrases", []),
                tone_spectrum=char_data.get("tone_spectrum", {}),
                translation_notes=char_data.get("translation_notes", {}),
                relationship_speech=self._relationship_speech(
                    char_data.get("relationship_speech", {})
                ),
                provenance=provenance,
            )
            StateManager.upsert_character(self.project_dir, char_state)

        for term_data in result.terms:
            provenance = term_data.get("provenance", {})
            if not isinstance(provenance, dict):
                provenance = {}
            provenance = {"source": "learning_engine", **provenance}
            term_state = TermState(
                term_id=term_data.get("term_id", ""),
                term_jp=term_data.get("term_jp", ""),
                term_zh=term_data.get("term_zh", ""),
                candidate_translations=[
                    str(item) for item in term_data.get("candidate_translations", [])
                ],
                context=term_data.get("context", ""),
                cultural_weight=term_data.get("cultural_weight", ""),
                strategy=term_data.get("strategy", ""),
                accepted_reason=str(term_data.get("accepted_reason", "")),
                rejected_reasons={
                    str(candidate): str(reason)
                    for candidate, reason in term_data.get("rejected_reasons", {}).items()
                } if isinstance(term_data.get("rejected_reasons"), dict) else {},
                applicability_scope=str(term_data.get("applicability_scope", "")),
                provenance=provenance,
                pending_human_review=True,
                frequency=term_data.get("frequency", 0),
            )
            StateManager.upsert_term(self.project_dir, term_state)

        logger.info("Seeded %d characters and %d terms into memory state",
                     len(result.characters), len(result.terms))
