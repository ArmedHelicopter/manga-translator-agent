"""Tests for mga.memory.graph — CharacterGraph."""

from pathlib import Path

from mga.memory.graph import CharacterGraph, FORMALITY_LEVELS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _two_char_graph() -> CharacterGraph:
    """Graph with two characters and one relationship."""
    g = CharacterGraph()
    g.add_character("tanaka", name="田中")
    g.add_character("sato", name="佐藤")
    g.add_relationship(
        "tanaka", "sato",
        relationship="classmate",
        formality="polite",
        honorific="さん",
    )
    return g


# ---------------------------------------------------------------------------
# Node tests
# ---------------------------------------------------------------------------

def test_add_character():
    g = CharacterGraph()
    g.add_character("tanaka", name="田中")
    assert "tanaka" in g.graph
    assert g.graph.nodes["tanaka"]["name"] == "田中"


def test_add_relationship():
    g = _two_char_graph()
    edge = g.get_relationship("tanaka", "sato")
    assert edge is not None
    assert edge["relationship"] == "classmate"
    assert edge["formality"] == "polite"
    assert edge["honorific"] == "さん"


# ---------------------------------------------------------------------------
# Getter tests
# ---------------------------------------------------------------------------

def test_get_relationship_found():
    g = _two_char_graph()
    edge = g.get_relationship("tanaka", "sato")
    assert isinstance(edge, dict)
    assert edge["formality"] == "polite"


def test_get_relationship_not_found():
    g = _two_char_graph()
    assert g.get_relationship("sato", "tanaka") is None


def test_get_formality():
    g = _two_char_graph()
    assert g.get_formality("tanaka", "sato") == "polite"


def test_get_formality_default():
    """No edge => default 'casual'."""
    g = _two_char_graph()
    assert g.get_formality("sato", "tanaka") == "casual"


def test_get_honorific():
    g = _two_char_graph()
    assert g.get_honorific("tanaka", "sato") == "さん"


def test_invalid_formality_fallback():
    """Invalid formality string defaults to 'casual'."""
    g = CharacterGraph()
    g.add_character("a")
    g.add_character("b")
    g.add_relationship("a", "b", formality="INVALID_LEVEL")
    assert g.get_formality("a", "b") == "casual"


# ---------------------------------------------------------------------------
# Relationship aggregation
# ---------------------------------------------------------------------------

def test_get_all_relationships():
    g = CharacterGraph()
    g.add_character("a")
    g.add_character("b")
    g.add_character("c")
    g.add_relationship("a", "b", relationship="friend")
    g.add_relationship("a", "c", relationship="rival")

    result = g.get_all_relationships("a")
    assert set(result.keys()) == {"b", "c"}
    assert result["b"]["relationship"] == "friend"
    assert result["c"]["relationship"] == "rival"


def test_get_incoming_relationships():
    g = CharacterGraph()
    g.add_character("a")
    g.add_character("b")
    g.add_relationship("a", "b", relationship="friend")
    g.add_relationship("b", "a", relationship="rival")

    incoming = g.get_incoming_relationships("a")
    assert "b" in incoming
    assert incoming["b"]["relationship"] == "rival"


# ---------------------------------------------------------------------------
# Path finding
# ---------------------------------------------------------------------------

def test_find_path():
    g = CharacterGraph()
    g.add_character("a")
    g.add_character("b")
    g.add_character("c")
    g.add_relationship("a", "b", relationship="friend")
    g.add_relationship("b", "c", relationship="colleague")

    path = g.find_path("a", "c")
    assert path == ["a", "b", "c"]


def test_find_path_no_path():
    g = CharacterGraph()
    g.add_character("a")
    g.add_character("b")
    # No edges connecting them
    assert g.find_path("a", "b") is None


def test_find_path_nonexistent_node():
    g = CharacterGraph()
    g.add_character("a")
    assert g.find_path("a", "ghost") is None


# ---------------------------------------------------------------------------
# Translation context
# ---------------------------------------------------------------------------

def test_get_context_for_translation():
    g = _two_char_graph()
    ctx = g.get_context_for_translation("tanaka", "sato")
    assert ctx["speaker"] == "tanaka"
    assert ctx["listener"] == "sato"
    assert ctx["formality"] == "polite"
    assert ctx["honorific"] == "さん"
    assert ctx["relationship"] == "classmate"


def test_get_context_for_translation_no_edge():
    g = _two_char_graph()
    ctx = g.get_context_for_translation("sato", "tanaka")
    assert ctx == {}


# ---------------------------------------------------------------------------
# Serialization round-trips
# ---------------------------------------------------------------------------

def test_save_and_load(tmp_path: Path):
    g = _two_char_graph()
    g.save(tmp_path)

    loaded = CharacterGraph.load(tmp_path)
    assert loaded.get_formality("tanaka", "sato") == "polite"
    assert loaded.get_honorific("tanaka", "sato") == "さん"


def test_to_dict_and_from_dict():
    g = _two_char_graph()
    data = g.to_dict()
    restored = CharacterGraph.from_dict(data)
    assert restored.get_formality("tanaka", "sato") == "polite"
    assert restored.get_honorific("tanaka", "sato") == "さん"
    assert restored.graph.number_of_nodes() == 2
    assert restored.graph.number_of_edges() == 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_load_missing_file(tmp_path: Path):
    """Loading from a directory with no graph file returns empty graph."""
    loaded = CharacterGraph.load(tmp_path)
    assert loaded.graph.number_of_nodes() == 0


def test_empty_graph_queries():
    g = CharacterGraph()
    g.add_character("lonely")
    assert g.get_all_relationships("lonely") == {}
    assert g.get_incoming_relationships("lonely") == {}
    assert g.get_context_for_translation("lonely", "ghost") == {}
    assert g.find_path("lonely", "ghost") is None
