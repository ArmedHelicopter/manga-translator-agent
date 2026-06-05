"""Tests for graph construction from learning and translation history."""

from mga.learning.models import LearningResult
from mga.memory.entities import CharacterState
from mga.memory.graph import CharacterGraph
from mga.memory.graph_builder import (
    build_and_save,
    build_graph_from_learning_result,
    infer_relationships_from_pages,
)
from mga.memory.state import StateManager
from mga.models.page import Bubble, Page
from mga.models.translation import TranslationCandidate


def test_build_graph_from_learning_result_adds_nodes_and_edges():
    learning_result = LearningResult(
        character_graph={
            "nodes": [
                {"id": "akari", "label": "Akari"},
                {"id": "ren", "label": "Ren"},
            ],
            "edges": [
                {
                    "source": "akari",
                    "target": "ren",
                    "relationship": "senpai",
                    "formality": "polite",
                    "honorific": "san",
                }
            ],
        }
    )

    graph = build_graph_from_learning_result(learning_result)

    assert "akari" in graph.graph.nodes
    assert graph.graph.nodes["akari"]["name_jp"] == "Akari"
    assert graph.get_relationship("akari", "ren")["relationship"] == "senpai"
    assert graph.get_formality("akari", "ren") == "polite"
    assert graph.get_honorific("akari", "ren") == "san"


def test_build_and_save_includes_persisted_character_state(tmp_path):
    StateManager.upsert_character(
        tmp_path,
        CharacterState(
            character_id="akari",
            name_jp="Akari",
            name_zh="Akari",
            archetype="lead",
        ),
    )

    graph = build_and_save(tmp_path)
    loaded = CharacterGraph.load(tmp_path)

    assert "akari" in graph.graph.nodes
    assert loaded.graph.nodes["akari"]["name_jp"] == "Akari"
    assert (tmp_path / "memory" / "state" / "character_graph.json").exists()


def test_infer_relationships_from_page_cooccurrence_adds_reciprocal_edges():
    pages = []
    translations = []
    for index in range(3):
        bubble_a = Bubble(
            bubble_id=f"p{index}-a",
            source_text="hello",
            speaker_id="akari",
        )
        bubble_b = Bubble(
            bubble_id=f"p{index}-b",
            source_text="hello",
            speaker_id="ren",
        )
        pages.append(Page(page_id=f"p{index}", bubbles=[bubble_a, bubble_b]))
        translations.extend([
            TranslationCandidate(bubble_id=bubble_a.bubble_id, text="hello"),
            TranslationCandidate(bubble_id=bubble_b.bubble_id, text="hello"),
        ])

    graph = infer_relationships_from_pages(pages, translations, CharacterGraph())

    assert graph.get_relationship("akari", "ren")["relationship"] == "frequent_interactor"
    assert graph.get_formality("akari", "ren") == "casual"
    assert graph.get_relationship("ren", "akari")["relationship"] == "frequent_interactor"
