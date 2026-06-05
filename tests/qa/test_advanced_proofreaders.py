"""Focused tests for advanced deterministic QA proofreaders."""

from mga.models import (
    BoundingBox,
    Bubble,
    Page,
    PageImage,
    TranslationCandidate,
)
from mga.qa.base import QAFeedbackType
from mga.qa.character_consistency import CharacterConsistencyProofreader
from mga.qa.dialog_hierarchy import DialogHierarchyProofreader
from mga.qa.emotion_consistency import EmotionConsistencyProofreader
from mga.qa.language_evolution import LanguageEvolutionProofreader
from mga.qa.style_polish import StylePolishProofreader


def _make_page(*bubbles: Bubble, scene_summary: str = "") -> Page:
    return Page(
        page_id="p1",
        image=PageImage(path="test.png"),
        scene_summary=scene_summary,
        bubbles=list(bubbles),
    )


def _categories(feedbacks) -> set[str]:
    return {feedback.category for feedback in feedbacks}


def test_dialog_hierarchy_reports_register_and_address_violations():
    reader = DialogHierarchyProofreader()
    page = _make_page(
        Bubble(
            bubble_id="b1",
            source_text="Please listen...",
            speaker_id="akari",
        ),
    )
    translations = [
        TranslationCandidate(bubble_id="b1", text="Boss, listen up!"),
    ]

    feedbacks = reader.proofread(
        page,
        translations,
        {
            "current_interlocutor": "ren",
            "character_graph": {
                "akari->ren": {"register": "formal"},
            },
            "address_rules": {
                "akari": {"forbidden": ["boss"]},
            },
        },
    )

    assert _categories(feedbacks) == {
        "hierarchy.register_violation",
        "hierarchy.address_violation",
    }
    assert {feedback.feedback_type for feedback in feedbacks} == {
        QAFeedbackType.ERROR,
        QAFeedbackType.WARNING,
    }


def test_character_consistency_reports_relationship_speech_violations():
    reader = CharacterConsistencyProofreader()
    page = _make_page(
        Bubble(
            bubble_id="b1",
            source_text="Please listen...",
            speaker_id="akari",
        ),
    )
    translations = [
        TranslationCandidate(bubble_id="b1", text="Boss, listen up!"),
    ]

    feedbacks = reader.proofread(
        page,
        translations,
        {
            "active_listeners": {"b1": "ren"},
            "character_profiles": {
                "akari": {
                    "relationship_speech": {
                        "ren": {
                            "address": "Sensei",
                            "required_terms": ["please"],
                            "forbidden_terms": ["boss"],
                        },
                    },
                },
            },
        },
    )

    assert _categories(feedbacks) == {
        "character.relationship_speech_missing",
        "character.relationship_speech_forbidden",
    }
    assert all(feedback.feedback_type == QAFeedbackType.WARNING for feedback in feedbacks)


def test_emotion_consistency_reports_scene_mismatch_and_progression_jump():
    reader = EmotionConsistencyProofreader()
    page = _make_page(
        Bubble(
            bubble_id="b1",
            source_text="This is serious",
            tone="comedy",
        ),
        Bubble(
            bubble_id="b2",
            source_text="Charge",
        ),
        scene_summary="battle climax",
    )
    translations = [
        TranslationCandidate(bubble_id="b1", text="Just kidding"),
        TranslationCandidate(bubble_id="b2", text="Go!!"),
    ]

    feedbacks = reader.proofread(
        page,
        translations,
        {"previous_page_emotions": ["sadness"]},
    )

    assert _categories(feedbacks) == {
        "emotion.scene_mismatch",
        "emotion.progression_jump",
    }


def test_language_evolution_reports_retired_and_missing_new_patterns():
    reader = LanguageEvolutionProofreader()
    page = _make_page(
        Bubble(
            bubble_id="b1",
            source_text="old catchphrase",
            speaker_id="akari",
            speaker_name="Akari",
        ),
    )
    translations = [
        TranslationCandidate(bubble_id="b1", text="old catchphrase"),
    ]

    feedbacks = reader.proofread(
        page,
        translations,
        {
            "chapter_number": 4,
            "voice_evolutions": {
                "akari": [
                    {
                        "retire_at_chapter": 3,
                        "adopt_at_chapter": 3,
                        "old_patterns": ["old catchphrase"],
                        "new_pattern": "new catchphrase",
                    },
                ],
            },
        },
    )

    assert _categories(feedbacks) == {
        "evolution.retired_pattern",
        "evolution.missing_new_pattern",
    }
    assert all(feedback.bubble_id == "b1" for feedback in feedbacks)


def test_style_polish_reports_punctuation_formatting_and_overflow_risks():
    reader = StylePolishProofreader()
    page = _make_page(
        Bubble(
            bubble_id="b1",
            source_text="Long text",
            bbox=BoundingBox(width=10, height=10),
        ),
    )
    translations = [
        TranslationCandidate(bubble_id="b1", text='hello,world  still going",'),
    ]

    feedbacks = reader.proofread(
        page,
        translations,
        {"target_lang": "zh-CN"},
    )

    assert _categories(feedbacks) == {
        "style.punctuation_western",
        "style.unpaired_quote",
        "style.double_space",
        "style.trailing_punctuation",
        "style.overflow_risk",
    }
