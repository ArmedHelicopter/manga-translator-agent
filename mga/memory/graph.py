"""Character relationship graph — NetworkX-based relationship network."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import networkx as nx

logger = logging.getLogger(__name__)

# Edge attributes
FORMALITY_LEVELS = {"intimate", "casual", "polite", "formal", "honorific"}


class CharacterGraph:
    """A directed graph of character relationships.

    Nodes: character_id (str)
    Edges: relationship with formality level, honorific rules, and evolution.
    """

    def __init__(self) -> None:
        self._graph = nx.DiGraph()

    @property
    def graph(self) -> nx.DiGraph:
        return self._graph

    def add_character(self, character_id: str, **attrs: Any) -> None:
        """Add a character node."""
        self._graph.add_node(character_id, **attrs)

    def add_relationship(
        self,
        source: str,
        target: str,
        relationship: str = "",
        formality: str = "casual",
        honorific: str = "",
        notes: str = "",
        **attrs: Any,
    ) -> None:
        """Add a directed relationship edge from source to target.

        Args:
            source: Speaker character_id.
            target: Listener character_id.
            relationship: Description (e.g. "classmate", "superior").
            formality: One of FORMALITY_LEVELS.
            honorific: Honorific used when source addresses target (e.g. "さん", "くん").
            notes: Additional notes.
        """
        if formality not in FORMALITY_LEVELS:
            logger.warning("Unknown formality '%s', defaulting to 'casual'", formality)
            formality = "casual"

        self._graph.add_edge(
            source, target,
            relationship=relationship,
            formality=formality,
            honorific=honorific,
            notes=notes,
            **attrs,
        )

    def get_relationship(self, source: str, target: str) -> dict[str, Any] | None:
        """Get the relationship edge from source to target."""
        if self._graph.has_edge(source, target):
            return dict(self._graph.edges[source, target])
        return None

    def get_formality(self, source: str, target: str) -> str:
        """Get the formality level for source → target communication."""
        edge = self.get_relationship(source, target)
        if edge:
            return edge.get("formality", "casual")
        return "casual"

    def get_honorific(self, source: str, target: str) -> str:
        """Get the honorific source uses when addressing target."""
        edge = self.get_relationship(source, target)
        if edge:
            return edge.get("honorific", "")
        return ""

    def get_all_relationships(self, character_id: str) -> dict[str, dict[str, Any]]:
        """Get all outgoing relationships for a character."""
        result = {}
        if character_id in self._graph:
            for _, target, data in self._graph.out_edges(character_id, data=True):
                result[target] = dict(data)
        return result

    def get_incoming_relationships(self, character_id: str) -> dict[str, dict[str, Any]]:
        """Get all incoming relationships (who addresses this character)."""
        result = {}
        if character_id in self._graph:
            for source, _, data in self._graph.in_edges(character_id, data=True):
                result[source] = dict(data)
        return result

    def find_path(self, source: str, target: str) -> list[str] | None:
        """Find shortest path between two characters."""
        try:
            path = nx.shortest_path(self._graph, source, target)
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def get_context_for_translation(
        self,
        speaker: str,
        listener: str,
    ) -> dict[str, Any]:
        """Get relationship context for translation prompt injection.

        Returns a dict with formality, honorific, and relationship info
        that can be injected into the translation prompt.
        """
        edge = self.get_relationship(speaker, listener)
        if not edge:
            return {}

        return {
            "speaker": speaker,
            "listener": listener,
            "relationship": edge.get("relationship", ""),
            "formality": edge.get("formality", "casual"),
            "honorific": edge.get("honorific", ""),
            "notes": edge.get("notes", ""),
        }

    def save(self, project_dir: Path) -> None:
        """Save graph to JSON."""
        graph_path = project_dir / "memory" / "state" / "character_graph.json"
        graph_path.parent.mkdir(parents=True, exist_ok=True)

        data = nx.node_link_data(self._graph)
        graph_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info("Saved character graph with %d nodes, %d edges",
                     self._graph.number_of_nodes(), self._graph.number_of_edges())

    @classmethod
    def load(cls, project_dir: Path) -> CharacterGraph:
        """Load graph from JSON."""
        graph_path = project_dir / "memory" / "state" / "character_graph.json"
        instance = cls()

        if graph_path.exists():
            try:
                data = json.loads(graph_path.read_text(encoding="utf-8"))
                instance._graph = nx.node_link_graph(data, directed=True)
            except Exception as e:
                logger.warning("Failed to load character graph: %s", e)

        return instance

    def to_dict(self) -> dict[str, Any]:
        """Export graph as a dict for serialization."""
        return nx.node_link_data(self._graph)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CharacterGraph:
        """Create a graph from a dict."""
        instance = cls()
        instance._graph = nx.node_link_graph(data, directed=True)
        return instance
