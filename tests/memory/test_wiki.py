"""Tests for mga.memory.wiki — WikiProjection Markdown generation."""

from pathlib import Path

from mga.memory.entities import (
    CharacterState,
    DecisionState,
    MemoryIndex,
    SceneState,
    TermState,
)
from mga.memory.wiki import WikiProjection


def test_character_page_generation():
    ch = CharacterState(
        character_id="tanaka",
        name_jp="田中",
        name_zh="田中",
        archetype="hero",
        speech_patterns={"ending_だ": "assertive"},
        catchphrases=["よろしく"],
    )
    md = WikiProjection.generate_character_page(ch)
    assert "# 田中" in md
    assert "speech_patterns" in md.lower() or "Speech Patterns" in md
    assert "よろしく" in md


def test_character_page_generation_includes_relationship_speech():
    ch = CharacterState(
        character_id="akari",
        name_jp="Akari",
        relationship_speech={
            "ren": {
                "honorific_level": "polite",
                "self_ref": "boku",
            }
        },
    )

    md = WikiProjection.generate_character_page(ch)

    assert "## Relationship Speech" in md
    assert "- ren:" in md
    assert '"honorific_level": "polite"' in md
    assert '"self_ref": "boku"' in md


def test_character_page_generation_includes_structured_voice_evolutions():
    ch = CharacterState(
        character_id="akari",
        name_jp="Akari",
        voice_evolutions=[
            {
                "chapter": 2,
                "page": 4,
                "changes": [{"field": "tone_spectrum.formal", "old": "soft", "new": "cold"}],
            }
        ],
    )

    md = WikiProjection.generate_character_page(ch)

    assert "## Voice Evolutions" in md
    assert "- ch2:" in md
    assert '"page": 4' in md
    assert '"field": "tone_spectrum.formal"' in md


def test_character_page_generation_serializes_structured_provenance():
    ch = CharacterState(
        character_id="akari",
        name_jp="Akari",
        provenance={
            "evidence_lines": ["SOURCE_A"],
            "translation_observations": [
                {
                    "page_id": "p1",
                    "bubble_id": "b1",
                    "source_text": "SOURCE_A",
                    "translated_text": "TARGET_A",
                }
            ],
        },
    )

    md = WikiProjection.generate_character_page(ch)

    assert "## Provenance" in md
    assert '- evidence_lines: ["SOURCE_A"]' in md
    assert '"bubble_id": "b1"' in md
    assert '"translated_text": "TARGET_A"' in md


def test_scene_page_generation():
    sc = SceneState(
        scene_id="ch1_p1", chapter=1, page=1,
        scene_description="Battle scene",
        mood="intense",
        characters=["tanaka"],
        relationship_changes=["Tanaka stops trusting Ren"],
        key_dialogue=["I will not forgive you."],
        future_impact="Ren must earn trust in the next chapter",
    )
    md = WikiProjection.generate_scene_page(sc)
    assert "ch1 p1" in md
    assert "Battle scene" in md
    assert "tanaka" in md
    assert "Tanaka stops trusting Ren" in md
    assert "I will not forgive you." in md
    assert "Ren must earn trust" in md


def test_term_page_generation():
    t = TermState(
        term_id="katana", term_jp="刀", term_zh="刀",
        frequency=5, cultural_weight="high", strategy="preserve",
    )
    md = WikiProjection.generate_term_page(t)
    assert "# 刀" in md
    assert "frequency: 5" in md.lower()


def test_term_page_generation_includes_review_fields():
    t = TermState(
        term_id="glass_join",
        term_jp="glass join",
        term_zh="glass join",
        candidate_translations=["glass mending", "crystal join"],
        accepted_reason="Matches the established ritual term.",
        rejected_reasons={"crystal join": "Sounds like a material name."},
        applicability_scope="Use for the named repair art only.",
    )

    md = WikiProjection.generate_term_page(t)

    assert "## Candidate Translations" in md
    assert "- glass mending" in md
    assert "- crystal join" in md
    assert "## Accepted Reason" in md
    assert "Matches the established ritual term." in md
    assert "## Rejected Reasons" in md
    assert "- crystal join: Sounds like a material name." in md
    assert "## Applicability Scope" in md
    assert "Use for the named repair art only." in md


def test_term_page_generation_includes_provenance():
    t = TermState(
        term_id="glass_join",
        term_jp="glass join",
        provenance={
            "chapter": "ch08",
            "page": "p03",
            "bubble_id": "b7",
            "trigger": "first coined-term review",
        },
    )

    md = WikiProjection.generate_term_page(t)

    assert "## Provenance" in md
    assert "- chapter: ch08" in md
    assert "- page: p03" in md
    assert "- bubble_id: b7" in md
    assert "- trigger: first coined-term review" in md


def test_decision_page_generation():
    d = DecisionState(
        decision_id="dec_1", stage="translate",
        decision="Use calque for honorifics", confidence=0.85,
        rationale="Preserves cultural flavor",
    )
    md = WikiProjection.generate_decision_page(d)
    assert "Use calque" in md
    assert "0.85" in md


def test_decision_page_generation_includes_metadata():
    d = DecisionState(
        decision_id="review-p1-b1-accept",
        stage="review",
        input_ref="p1/b1",
        decision="accept repair_semantic_translation for b1",
        rationale="Human reviewer confirmed repair",
        metadata={
            "suggested_text": "new number",
            "original_text": "old number",
            "status": "accept",
        },
    )

    md = WikiProjection.generate_decision_page(d)

    assert "## Metadata" in md
    assert "- original_text: old number" in md
    assert "- status: accept" in md
    assert "- suggested_text: new number" in md
    assert md.index("- original_text: old number") < md.index("- status: accept")
    assert md.index("- status: accept") < md.index("- suggested_text: new number")


def test_index_page_generation():
    idx = MemoryIndex(
        characters={"t": "田中"}, scenes={"s1": "scene1"},
    )
    md = WikiProjection.generate_index(idx)
    assert "田中" in md
    assert "scene1" in md


def test_write_all_creates_files(tmp_path):
    ch = CharacterState(character_id="c1", name_jp="C1")
    idx = MemoryIndex(characters={"c1": "C1"})
    # Need to save entity first so StateManager can find it
    from mga.memory.state import StateManager
    StateManager.upsert_character(tmp_path, ch)
    StateManager.save(tmp_path, idx)

    WikiProjection.write_all(tmp_path, idx)
    assert (tmp_path / "memory" / "characters" / "c1.md").exists()
    assert (tmp_path / "memory" / "indexes" / "index.md").exists()
