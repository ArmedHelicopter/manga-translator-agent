"""Query functions for the character relationship graph."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .graph import CharacterGraph, FORMALITY_LEVELS


class GraphRetrieval:
    """Query interface for character relationships."""

    def __init__(self, graph: CharacterGraph) -> None:
        self._graph = graph

    @classmethod
    def from_project(cls, project_dir: Path) -> GraphRetrieval:
        """Load graph from project directory."""
        return cls(CharacterGraph.load(project_dir))

    def get_addressing(
        self,
        speaker: str,
        listener: str,
    ) -> dict[str, Any]:
        """Get how speaker should address listener.

        Returns:
            {
                "honorific": str,       # e.g. "さん", "くん", ""
                "formality": str,       # e.g. "polite", "casual"
                "relationship": str,    # e.g. "classmate", "superior"
                "suggestion": str,      # Human-readable suggestion
            }
        """
        context = self._graph.get_context_for_translation(speaker, listener)
        if not context:
            return {
                "honorific": "",
                "formality": "casual",
                "relationship": "",
                "suggestion": "No relationship data available; defaulting to casual.",
            }

        formality = context.get("formality", "casual")
        honorific = context.get("honorific", "")
        relationship = context.get("relationship", "")

        suggestion = self._build_suggestion(formality, honorific, relationship)
        return {
            "honorific": honorific,
            "formality": formality,
            "relationship": relationship,
            "suggestion": suggestion,
        }

    def get_translation_context(
        self,
        speaker: str,
        listener: str,
    ) -> str:
        """Get a formatted string for injection into translation prompts.

        Returns a Chinese-language section like:
        "关系上下文：A 对 B 说话时使用敬语（さん），关系=同学"
        """
        addressing = self.get_addressing(speaker, listener)
        if not addressing.get("relationship") and not addressing.get("honorific"):
            return ""

        parts = ["关系上下文："]
        if addressing["relationship"]:
            parts.append(f"关系={addressing['relationship']}")
        if addressing["formality"]:
            formality_zh = {
                "intimate": "亲密",
                "casual": "随意",
                "polite": "礼貌",
                "formal": "正式",
                "honorific": "敬语",
            }.get(addressing["formality"], addressing["formality"])
            parts.append(f"语气={formality_zh}")
        if addressing["honorific"]:
            parts.append(f"称呼={addressing['honorific']}")

        return "，".join(parts)

    def get_network_summary(self, character_id: str) -> dict[str, Any]:
        """Get a summary of a character's relationship network."""
        outgoing = self._graph.get_all_relationships(character_id)
        incoming = self._graph.get_incoming_relationships(character_id)

        return {
            "character_id": character_id,
            "addresses": {
                target: {
                    "formality": data.get("formality", "casual"),
                    "honorific": data.get("honorific", ""),
                    "relationship": data.get("relationship", ""),
                }
                for target, data in outgoing.items()
            },
            "addressed_by": {
                source: {
                    "formality": data.get("formality", "casual"),
                    "honorific": data.get("honorific", ""),
                    "relationship": data.get("relationship", ""),
                }
                for source, data in incoming.items()
            },
            "connection_count": len(outgoing) + len(incoming),
        }

    def check_formality_consistency(
        self,
        speaker: str,
        listener: str,
        proposed_formality: str,
    ) -> dict[str, Any]:
        """Check if a proposed formality level is consistent with known relationships.

        Returns:
            {
                "consistent": bool,
                "expected": str,      # The formality from the graph
                "proposed": str,      # The proposed formality
                "message": str,       # Explanation
            }
        """
        expected = self._graph.get_formality(speaker, listener)
        consistent = expected == proposed_formality

        if consistent:
            message = f"Formality '{proposed_formality}' matches expected '{expected}'."
        else:
            message = (
                f"Formality mismatch: expected '{expected}' for "
                f"{speaker}→{listener}, got '{proposed_formality}'."
            )

        return {
            "consistent": consistent,
            "expected": expected,
            "proposed": proposed_formality,
            "message": message,
        }

    def _build_suggestion(self, formality: str, honorific: str, relationship: str) -> str:
        """Build a human-readable suggestion."""
        formality_desc = {
            "intimate": "使用亲密语气",
            "casual": "使用随意语气",
            "polite": "使用礼貌语气",
            "formal": "使用正式语气",
            "honorific": "使用敬语",
        }.get(formality, f"语气={formality}")

        parts = [formality_desc]
        if honorific:
            parts.append(f"使用称呼「{honorific}」")
        if relationship:
            parts.append(f"（关系：{relationship}）")

        return "，".join(parts)
