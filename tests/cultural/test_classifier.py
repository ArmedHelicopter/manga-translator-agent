"""Tests for mga.cultural.classifier — cultural problem classification."""

from mga.cultural.classifier import CulturalProblemType, classify_problem


def test_honorific_detection():
    problems = classify_problem("田中さん", "")
    assert CulturalProblemType.HONORIFIC in problems


def test_honorific_sensei():
    problems = classify_problem("先生", "")
    assert CulturalProblemType.HONORIFIC in problems


def test_form_of_address():
    problems = classify_problem("お兄さん", "")
    assert CulturalProblemType.FORM_OF_ADDRESS in problems


def test_onomatopoeia_common():
    problems = classify_problem("ドキドキ", "")
    assert CulturalProblemType.ONOMATOPOEIA in problems


def test_onomatopoeia_katakana_pattern():
    problems = classify_problem("ガタガタ", "")
    assert CulturalProblemType.ONOMATOPOEIA in problems


def test_cultural_concept():
    problems = classify_problem("お花見", "春の")
    assert CulturalProblemType.CULTURAL_CONCEPT in problems


def test_cultural_concept_shrine():
    problems = classify_problem("神社", "参拝")
    assert CulturalProblemType.CULTURAL_CONCEPT in problems


def test_no_problems_for_plain_text():
    problems = classify_problem("hello", "")
    assert problems == []


def test_multiple_classifications():
    # お兄さん is both a form of address and could match other patterns
    problems = classify_problem("お兄さん", "")
    assert len(problems) >= 1
