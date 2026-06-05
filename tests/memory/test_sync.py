from __future__ import annotations

from pathlib import Path

from mga.memory.entities import CharacterState, DecisionState, SceneState, TermState
from mga.memory.state import StateManager
from mga.memory.sync import state_to_wiki, wiki_to_state
from mga.memory.wiki import WikiProjection, work_scoped_id


def test_state_to_wiki_writes_scene_projection(tmp_path: Path) -> None:
    StateManager.upsert_scene(
        tmp_path,
        SceneState(
            scene_id="ch1_p3",
            chapter=1,
            page=3,
            scene_description="Akari confronts Ren",
            mood="tense",
            characters=["akari", "ren"],
        ),
    )

    state_to_wiki(tmp_path)

    scene_md = tmp_path / "memory" / "scenes" / "ch1_p3.md"
    assert scene_md.exists()
    assert "Akari confronts Ren" in scene_md.read_text(encoding="utf-8")


def test_state_to_wiki_writes_work_scoped_term_projection(tmp_path: Path) -> None:
    StateManager.upsert_term(
        tmp_path,
        TermState(
            term_id=work_scoped_id("Glass Blade", "glass_join"),
            term_jp="glass join",
            term_zh="glass mending",
        ),
    )

    state_to_wiki(tmp_path, work="Glass Blade")

    term_md = tmp_path / "memory" / "terms" / "glass-blade" / "glass_join.md"
    assert term_md.exists()
    text = term_md.read_text(encoding="utf-8")
    assert "- Term ID: glass_join" in text
    assert not (tmp_path / "memory" / "terms" / "glass-blade__glass_join.md").exists()
    assert (tmp_path / "memory" / "indexes" / "glass-blade.md").exists()


def test_wiki_to_state_reads_work_scoped_term_projection(tmp_path: Path) -> None:
    term_md = tmp_path / "memory" / "terms" / "glass-blade" / "glass_join.md"
    term_md.parent.mkdir(parents=True)
    term_md.write_text(
        WikiProjection.generate_term_page(
            TermState(
                term_id="glass_join",
                term_jp="glass join",
                term_zh="glass mending",
            )
        ),
        encoding="utf-8",
    )

    wiki_to_state(tmp_path, work="Glass Blade")

    term = StateManager.get_term(tmp_path, "glass-blade__glass_join")
    assert term is not None
    assert term.term_jp == "glass join"
    assert term.term_zh == "glass mending"


def test_wiki_to_state_reads_generated_scene_projection(tmp_path: Path) -> None:
    scene_md = tmp_path / "memory" / "scenes" / "ch2_p5.md"
    scene_md.parent.mkdir(parents=True)
    scene_md.write_text(
        WikiProjection.generate_scene_page(
            SceneState(
                scene_id="ch2_p5",
                chapter=2,
                page=5,
                scene_description="Ren waits by the bridge",
                mood="somber",
                narrative_summary="The argument has not been resolved",
                characters=["ren"],
                relationship_changes=["Ren avoids Akari after the argument"],
                key_dialogue=["I need time."],
                future_impact="Akari enters the next scene alone",
            )
        ),
        encoding="utf-8",
    )

    wiki_to_state(tmp_path)

    scene = StateManager.get_scene(tmp_path, "ch2_p5")
    assert scene is not None
    assert scene.chapter == 2
    assert scene.page == 5
    assert scene.scene_description == "Ren waits by the bridge"
    assert scene.mood == "somber"
    assert scene.narrative_summary == "The argument has not been resolved"
    assert scene.characters == ["ren"]
    assert scene.relationship_changes == ["Ren avoids Akari after the argument"]
    assert scene.key_dialogue == ["I need time."]
    assert scene.future_impact == "Akari enters the next scene alone"


def test_wiki_to_state_preserves_index_label_edits(tmp_path: Path) -> None:
    StateManager.upsert_character(
        tmp_path,
        CharacterState(character_id="akari", name_jp="Akari"),
    )
    StateManager.upsert_scene(
        tmp_path,
        SceneState(scene_id="ch1_p1", chapter=1, page=1),
    )
    StateManager.upsert_decision(
        tmp_path,
        DecisionState(decision_id="d1", decision="Use honorific compensation"),
    )

    state_to_wiki(tmp_path)
    index_md = tmp_path / "memory" / "indexes" / "index.md"
    text = index_md.read_text(encoding="utf-8")
    text = text.replace("Akari (`akari`)", "Lead Lamp Girl (`akari`)")
    text = text.replace("ch1_p1 (`ch1_p1`)", "Opening Scene (`ch1_p1`)")
    text = text.replace(
        "Use honorific compensation (`d1`)",
        "Honorific Decision (`d1`)",
    )
    index_md.write_text(text, encoding="utf-8")

    wiki_to_state(tmp_path)

    index = StateManager.load(tmp_path)
    assert index.characters["akari"] == "Lead Lamp Girl"
    assert index.scenes["ch1_p1"] == "Opening Scene"
    assert index.decisions["d1"] == "Honorific Decision"


def test_wiki_to_state_preserves_character_provenance_markers(tmp_path: Path) -> None:
    character_md = tmp_path / "memory" / "characters" / "akari.md"
    character_md.parent.mkdir(parents=True)
    character_md.write_text(
        WikiProjection.generate_character_page(
            CharacterState(
                character_id="akari",
                name_jp="Akari",
                provenance={
                    "status": "deprecated",
                    "superseded_by": "akari_v2",
                    "last_reviewed_at": "2026-05-06T14:00:00Z",
                },
            )
        ),
        encoding="utf-8",
    )

    wiki_to_state(tmp_path)

    character = StateManager.get_character(tmp_path, "akari")
    assert character is not None
    assert character.provenance == {
        "status": "deprecated",
        "superseded_by": "akari_v2",
        "last_reviewed_at": "2026-05-06T14:00:00Z",
    }


def test_wiki_to_state_preserves_structured_character_provenance(tmp_path: Path) -> None:
    character_md = tmp_path / "memory" / "characters" / "akari.md"
    character_md.parent.mkdir(parents=True)
    character_md.write_text(
        WikiProjection.generate_character_page(
            CharacterState(
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
        ),
        encoding="utf-8",
    )

    wiki_to_state(tmp_path)

    character = StateManager.get_character(tmp_path, "akari")
    assert character is not None
    assert character.provenance["evidence_lines"] == ["SOURCE_A"]
    assert character.provenance["translation_observations"] == [
        {
            "page_id": "p1",
            "bubble_id": "b1",
            "source_text": "SOURCE_A",
            "translated_text": "TARGET_A",
        }
    ]


def test_wiki_to_state_preserves_character_relationship_speech(tmp_path: Path) -> None:
    character_md = tmp_path / "memory" / "characters" / "akari.md"
    character_md.parent.mkdir(parents=True)
    character_md.write_text(
        WikiProjection.generate_character_page(
            CharacterState(
                character_id="akari",
                name_jp="Akari",
                relationship_speech={
                    "ren": {
                        "honorific_level": "polite",
                        "self_ref": "boku",
                        "required_terms": ["Sensei"],
                    }
                },
            )
        ),
        encoding="utf-8",
    )

    wiki_to_state(tmp_path)

    character = StateManager.get_character(tmp_path, "akari")
    assert character is not None
    assert character.relationship_speech == {
        "ren": {
            "honorific_level": "polite",
            "self_ref": "boku",
            "required_terms": ["Sensei"],
        }
    }


def test_wiki_to_state_preserves_character_notes_and_voice_evolutions(
    tmp_path: Path,
) -> None:
    character_md = tmp_path / "memory" / "characters" / "akari.md"
    character_md.parent.mkdir(parents=True)
    character_md.write_text(
        WikiProjection.generate_character_page(
            CharacterState(
                character_id="akari",
                name_jp="Akari",
                translation_notes={
                    "honorific": "keep teacher address formal",
                    "first_person": "use I only after ch3",
                },
                voice_evolutions=[
                    {
                        "chapter": 3,
                        "page": 7,
                        "changes": [
                            {
                                "field": "speech_patterns.self_ref",
                                "old": "boku",
                                "new": "ore",
                            }
                        ],
                        "timestamp": "2026-05-06T12:00:00",
                    }
                ],
            )
        ),
        encoding="utf-8",
    )

    wiki_to_state(tmp_path)

    character = StateManager.get_character(tmp_path, "akari")
    assert character is not None
    assert character.translation_notes == {
        "honorific": "keep teacher address formal",
        "first_person": "use I only after ch3",
    }
    assert character.voice_evolutions == [
        {
            "chapter": 3,
            "page": 7,
            "changes": [
                {
                    "field": "speech_patterns.self_ref",
                    "old": "boku",
                    "new": "ore",
                }
            ],
            "timestamp": "2026-05-06T12:00:00",
        }
    ]


def test_wiki_to_state_preserves_decision_input_ref_and_metadata(tmp_path: Path) -> None:
    decision_md = tmp_path / "memory" / "decisions" / "review-p1-b1-accept.md"
    decision_md.parent.mkdir(parents=True)
    decision_md.write_text(
        WikiProjection.generate_decision_page(
            DecisionState(
                decision_id="review-p1-b1-accept",
                stage="review",
                input_ref="p1/b1",
                decision=(
                    "accept repair_semantic_translation for b1\n"
                    "keep the lower-confidence alternative as audit context"
                ),
                rationale=(
                    "Human reviewer confirmed repair.\n"
                    "The original dropped a numeric detail."
                ),
                confidence=0.82,
                metadata={
                    "original_text": "old number",
                    "status": "accept",
                    "suggested_text": "new number",
                },
            )
        ),
        encoding="utf-8",
    )

    wiki_to_state(tmp_path)

    decision = StateManager.get_decision(tmp_path, "review-p1-b1-accept")
    assert decision is not None
    assert decision.input_ref == "p1/b1"
    assert decision.decision == (
        "accept repair_semantic_translation for b1\n"
        "keep the lower-confidence alternative as audit context"
    )
    assert decision.rationale == (
        "Human reviewer confirmed repair.\n"
        "The original dropped a numeric detail."
    )
    assert decision.metadata == {
        "original_text": "old number",
        "status": "accept",
        "suggested_text": "new number",
    }


def test_wiki_to_state_preserves_term_review_fields(tmp_path: Path) -> None:
    term_md = tmp_path / "memory" / "terms" / "glass_join.md"
    term_md.parent.mkdir(parents=True)
    term_md.write_text(
        WikiProjection.generate_term_page(
            TermState(
                term_id="glass_join",
                term_jp="glass join",
                term_zh="glass join",
                context="A recurring fictional repair technique.",
                candidate_translations=["glass mending", "crystal join"],
                accepted_reason="Matches the established ritual term.",
                rejected_reasons={"crystal join": "Sounds like a material name."},
                applicability_scope="Use for the named repair art only.",
            )
        ),
        encoding="utf-8",
    )

    wiki_to_state(tmp_path)

    term = StateManager.get_term(tmp_path, "glass_join")
    assert term is not None
    assert term.context == "A recurring fictional repair technique."
    assert term.candidate_translations == ["glass mending", "crystal join"]
    assert term.accepted_reason == "Matches the established ritual term."
    assert term.rejected_reasons == {"crystal join": "Sounds like a material name."}
    assert term.applicability_scope == "Use for the named repair art only."


def test_wiki_to_state_preserves_term_provenance(tmp_path: Path) -> None:
    term_md = tmp_path / "memory" / "terms" / "glass_join.md"
    term_md.parent.mkdir(parents=True)
    term_md.write_text(
        WikiProjection.generate_term_page(
            TermState(
                term_id="glass_join",
                term_jp="glass join",
                provenance={
                    "chapter": "ch08",
                    "page": "p03",
                    "bubble_id": "b7",
                    "trigger": "first coined-term review",
                    "evidence": ["source bubble", "human note"],
                },
            )
        ),
        encoding="utf-8",
    )

    wiki_to_state(tmp_path)

    term = StateManager.get_term(tmp_path, "glass_join")
    assert term is not None
    assert term.provenance == {
        "chapter": "ch08",
        "page": "p03",
        "bubble_id": "b7",
        "trigger": "first coined-term review",
        "evidence": ["source bubble", "human note"],
    }
