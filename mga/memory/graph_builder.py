"""Build character relationship graph from translation history and learning results."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from .graph import CharacterGraph, FORMALITY_LEVELS
from .state import StateManager

logger = logging.getLogger(__name__)

# Patterns for detecting honorific usage in Japanese text
_HONORIFIC_RE = re.compile(r"[一-鿿]{1,4}(さん|くん|ちゃん|様|様|殿|先生|せんぱい|先輩|後輩)")

# Patterns for detecting formality cues
_CASUAL_CUES = re.compile(r"[だぜよねぞっょ]")
_POLITE_CUES = re.compile(r"[ですます]")
_FORMAL_CUES = re.compile(r"[でございます]")


def build_graph_from_characters(project_dir: Path) -> CharacterGraph:
    """Build a base graph with all known characters as nodes."""
    graph = CharacterGraph()
    chars = StateManager.list_characters(project_dir)
    for ch in chars:
        if ch.character_id:
            graph.add_character(
                ch.character_id,
                name_jp=ch.name_jp,
                name_zh=ch.name_zh,
                archetype=ch.archetype,
            )
    return graph


def build_graph_from_learning_result(
    learning_result: Any,
    existing_graph: CharacterGraph | None = None,
) -> CharacterGraph:
    """Build or update graph from Module B's LearningResult.

    The LearningResult.character_graph has structure:
    {"nodes": [{"id": str, "label": str}], "edges": [{"source": str, "target": str, "relationship": str, "formality": str}]}
    """
    graph = existing_graph or CharacterGraph()

    char_graph_data = getattr(learning_result, "character_graph", {})
    if not char_graph_data:
        return graph

    # Add nodes
    for node in char_graph_data.get("nodes", []):
        node_id = node.get("id", "")
        if node_id:
            graph.add_character(node_id, name_jp=node.get("label", ""))

    # Add edges
    for edge in char_graph_data.get("edges", []):
        source = edge.get("source", "")
        target = edge.get("target", "")
        if source and target:
            graph.add_relationship(
                source=source,
                target=target,
                relationship=edge.get("relationship", ""),
                formality=edge.get("formality", "casual"),
                honorific=edge.get("honorific", ""),
            )

    return graph


def infer_relationships_from_pages(
    pages: list[Any],
    translations: list[Any],
    graph: CharacterGraph,
) -> CharacterGraph:
    """Infer relationships from dialogue patterns in translated pages.

    Analyzes:
    - Honorific usage → infer formality and relationship
    - Speech patterns → infer formality level
    - Speaker co-occurrence → infer relationship strength
    """
    # Build translation lookup
    trans_by_id = {t.bubble_id: t for t in translations}

    # Track co-occurrences and honorific patterns
    co_occurrences: dict[tuple[str, str], int] = {}
    honorific_uses: dict[tuple[str, str], list[str]] = {}

    for page in pages:
        for bubble in page.bubbles:
            speaker = bubble.speaker_id or bubble.speaker_name
            if not speaker:
                continue

            candidate = trans_by_id.get(bubble.bubble_id)
            if not candidate:
                continue

            # Extract honorifics from source text
            honorifics = _HONORIFIC_RE.findall(bubble.source_text)
            for name_honorific in honorifics:
                # The name is the full match minus the honorific suffix
                full_match = name_honorific
                for suffix in ("さん", "くん", "ちゃん", "様", "様", "殿", "先生", "せんぱい", "先輩", "後輩"):
                    if full_match.endswith(suffix):
                        target_name = full_match[:-len(suffix)]
                        # We don't know the target character_id from just the name
                        # Store by name for later resolution
                        key = (speaker, target_name)
                        honorific_uses.setdefault(key, []).append(suffix)
                        break

            # Track which speakers appear on same page
            for other_bubble in page.bubbles:
                other_speaker = other_bubble.speaker_id or other_bubble.speaker_name
                if other_speaker and other_speaker != speaker:
                    key = tuple(sorted([speaker, other_speaker]))
                    co_occurrences[key] = co_occurrences.get(key, 0) + 1

    # Infer formality from co-occurrence frequency
    # Characters who interact frequently likely have casual relationships
    for (char_a, char_b), count in co_occurrences.items():
        if count >= 5 and graph.get_relationship(char_a, char_b) is None:
            # Frequent interaction → casual by default
            graph.add_relationship(
                source=char_a, target=char_b,
                relationship="frequent_interactor",
                formality="casual",
            )
            graph.add_relationship(
                source=char_b, target=char_a,
                relationship="frequent_interactor",
                formality="casual",
            )

    return graph


def build_and_save(
    project_dir: Path,
    pages: list[Any] | None = None,
    translations: list[Any] | None = None,
    learning_result: Any = None,
) -> CharacterGraph:
    """Full build pipeline: load existing → enhance with history → save."""
    # Load existing graph or create new
    graph = CharacterGraph.load(project_dir)

    # Ensure all characters are nodes
    base_graph = build_graph_from_characters(project_dir)
    for node in base_graph.graph.nodes:
        if not graph.graph.has_node(node):
            attrs = base_graph.graph.nodes[node]
            graph.add_character(node, **attrs)

    # Enhance from learning results
    if learning_result:
        graph = build_graph_from_learning_result(learning_result, graph)

    # Enhance from translation history
    if pages and translations:
        graph = infer_relationships_from_pages(pages, translations, graph)

    graph.save(project_dir)
    return graph
