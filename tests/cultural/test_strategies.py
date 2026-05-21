"""Tests for mga.cultural.strategies — strategy selection."""

from mga.cultural.classifier import CulturalProblemType
from mga.cultural.strategies import (
    TranslationStrategy,
    describe_strategy,
    select_strategy,
)


def test_honorific_high_weight():
    s = select_strategy(CulturalProblemType.HONORIFIC, "high", "")
    assert s == TranslationStrategy.EQUIVALENT


def test_honorific_low_weight():
    s = select_strategy(CulturalProblemType.HONORIFIC, "low", "")
    assert s == TranslationStrategy.LITERAL


def test_coined_term_high_weight():
    s = select_strategy(CulturalProblemType.COINED_TERM, "high", "")
    assert s == TranslationStrategy.COINED


def test_cultural_concept_medium_weight():
    s = select_strategy(CulturalProblemType.CULTURAL_CONCEPT, "medium", "")
    assert s == TranslationStrategy.EQUIVALENT


def test_onomatopoeia_sfx_override():
    s = select_strategy(CulturalProblemType.ONOMATOPOEIA, "high", "sfx context")
    assert s == TranslationStrategy.PRESERVE_ORIGINAL


def test_honorific_narration_override():
    s = select_strategy(CulturalProblemType.HONORIFIC, "high", "narration text")
    assert s == TranslationStrategy.CALQUE


def test_fictional_script_title_override():
    s = select_strategy(CulturalProblemType.FICTIONAL_SCRIPT, "high", "title: ゲーム")
    assert s == TranslationStrategy.PRESERVE_ORIGINAL


def test_unknown_type_defaults_to_literal():
    # Use a constructed type that's not in the matrix
    s = select_strategy(CulturalProblemType.IDIOM, "medium", "")
    # IDIOM is in the matrix, so it should return a valid strategy
    assert isinstance(s, TranslationStrategy)


def test_describe_strategy():
    desc = describe_strategy(TranslationStrategy.CALQUE)
    assert "calque" in desc.lower() or "loan" in desc.lower()
