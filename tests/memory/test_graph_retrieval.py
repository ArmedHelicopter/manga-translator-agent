"""Tests for mga.memory.graph_retrieval — GraphRetrieval."""

from pathlib import Path

from mga.memory.graph import CharacterGraph
from mga.memory.graph_retrieval import GraphRetrieval


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_retrieval() -> tuple[GraphRetrieval, CharacterGraph]:
    """Graph with tanaka -> sato (polite/さん/classmate)."""
    g = CharacterGraph()
    g.add_character("tanaka", name="田中")
    g.add_character("sato", name="佐藤")
    g.add_relationship(
        "tanaka", "sato",
        relationship="classmate",
        formality="polite",
        honorific="さん",
    )
    return GraphRetrieval(g), g


# ---------------------------------------------------------------------------
# get_addressing
# ---------------------------------------------------------------------------

def test_get_addressing_with_relationship():
    gr, _ = _make_retrieval()
    result = gr.get_addressing("tanaka", "sato")
    assert result["honorific"] == "さん"
    assert result["formality"] == "polite"
    assert result["relationship"] == "classmate"
    assert isinstance(result["suggestion"], str)
    assert len(result["suggestion"]) > 0


def test_get_addressing_no_relationship():
    gr, _ = _make_retrieval()
    result = gr.get_addressing("sato", "tanaka")
    assert result["honorific"] == ""
    assert result["formality"] == "casual"
    assert result["relationship"] == ""
    assert "casual" in result["suggestion"].lower() or "default" in result["suggestion"].lower()


# ---------------------------------------------------------------------------
# get_translation_context
# ---------------------------------------------------------------------------

def test_get_translation_context():
    gr, _ = _make_retrieval()
    ctx = gr.get_translation_context("tanaka", "sato")
    # Should be a non-empty Chinese-formatted string
    assert isinstance(ctx, str)
    assert len(ctx) > 0
    assert "关系上下文" in ctx
    assert "classmate" in ctx
    assert "礼貌" in ctx  # polite -> 礼貌
    assert "さん" in ctx


def test_get_translation_context_empty():
    gr, _ = _make_retrieval()
    ctx = gr.get_translation_context("sato", "tanaka")
    assert ctx == ""


# ---------------------------------------------------------------------------
# get_network_summary
# ---------------------------------------------------------------------------

def test_get_network_summary():
    gr, g = _make_retrieval()
    summary = gr.get_network_summary("tanaka")
    assert summary["character_id"] == "tanaka"
    assert "sato" in summary["addresses"]
    assert summary["addresses"]["sato"]["formality"] == "polite"
    assert summary["addressed_by"] == {}  # nobody points at tanaka
    assert summary["connection_count"] == 1


def test_get_network_summary_bidirectional():
    g = CharacterGraph()
    g.add_character("a")
    g.add_character("b")
    g.add_relationship("a", "b", relationship="friend")
    g.add_relationship("b", "a", relationship="rival")

    gr = GraphRetrieval(g)
    summary = gr.get_network_summary("a")
    assert "b" in summary["addresses"]
    assert "b" in summary["addressed_by"]
    assert summary["connection_count"] == 2


# ---------------------------------------------------------------------------
# check_formality_consistency
# ---------------------------------------------------------------------------

def test_check_formality_consistent():
    gr, _ = _make_retrieval()
    result = gr.check_formality_consistency("tanaka", "sato", "polite")
    assert result["consistent"] is True
    assert result["expected"] == "polite"
    assert result["proposed"] == "polite"
    assert "matches" in result["message"].lower()


def test_check_formality_inconsistent():
    gr, _ = _make_retrieval()
    result = gr.check_formality_consistency("tanaka", "sato", "casual")
    assert result["consistent"] is False
    assert result["expected"] == "polite"
    assert result["proposed"] == "casual"
    assert "mismatch" in result["message"].lower()


def test_check_formality_no_edge():
    """No edge => expected is 'casual' (default)."""
    gr, _ = _make_retrieval()
    result = gr.check_formality_consistency("sato", "tanaka", "casual")
    assert result["consistent"] is True
    assert result["expected"] == "casual"


# ---------------------------------------------------------------------------
# from_project (integration-style)
# ---------------------------------------------------------------------------

def test_from_project(tmp_path: Path):
    g = CharacterGraph()
    g.add_character("x")
    g.add_character("y")
    g.add_relationship("x", "y", formality="formal", honorific="様")
    g.save(tmp_path)

    gr = GraphRetrieval.from_project(tmp_path)
    addressing = gr.get_addressing("x", "y")
    assert addressing["formality"] == "formal"
    assert addressing["honorific"] == "様"
