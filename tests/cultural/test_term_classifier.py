"""Tests for mga.cultural.term_classifier — 7-level term grading."""

from mga.cultural.term_classifier import (
    TermClassification,
    TermGrade,
    classify_batch,
    classify_term,
)


def test_classify_universal():
    """No problem types should yield G1_UNIVERSAL."""
    result = classify_term("太郎", [])
    assert result.grade == TermGrade.G1_UNIVERSAL
    assert result.strategy == "equivalent"


def test_classify_coined():
    """COINED_TERM problem type should yield G6_COINED."""
    result = classify_term("スーパーフォース", ["COINED_TERM"])
    assert result.grade == TermGrade.G6_COINED
    assert result.strategy == "preserve_original"


def test_classify_honorific():
    """HONORIFIC problem type should yield G5_CULTURAL."""
    result = classify_term("田中さん", ["HONORIFIC"])
    assert result.grade == TermGrade.G5_CULTURAL
    assert result.strategy == "explanatory"


def test_classify_fictional_script():
    """FICTIONAL_SCRIPT problem type should yield G7_FICTIONAL."""
    result = classify_term("☆ラテン語☆", ["FICTIONAL_SCRIPT"])
    assert result.grade == TermGrade.G7_FICTIONAL
    assert result.strategy == "preserve_original"


def test_classify_high_weight():
    """High cultural weight should upgrade G2/G3 to G5_CULTURAL."""
    result = classify_term("お花見", ["ONOMATOPOEIA"], cultural_weight="high")
    # ONOMATOPOEIA defaults to G3_LOANWORD, high weight upgrades G3 -> G5
    assert result.grade == TermGrade.G5_CULTURAL
    assert result.confidence == 0.8


def test_classify_low_weight():
    """Low cultural weight should downgrade G5/G6 to G4_CALQUE."""
    result = classify_term("刀", ["HONORIFIC"], cultural_weight="low")
    # HONORIFIC defaults to G5_CULTURAL, low weight downgrades G5 -> G4
    assert result.grade == TermGrade.G4_CALQUE
    assert result.confidence == 0.6


def test_classify_context_override_title():
    """Title/logo/sfx context should upgrade G3/G4 to G6_COINED."""
    result = classify_term(
        "ドキドキ", ["ONOMATOPOEIA"], context="title screen"
    )
    # ONOMATOPOEIA -> G3_LOANWORD, title context upgrades to G6_COINED
    assert result.grade == TermGrade.G6_COINED
    assert result.confidence == 0.8


def test_classify_batch():
    """classify_batch should classify multiple terms at once."""
    terms = [
        {"term_jp": "太郎", "problem_types": []},
        {"term_jp": "スーパーフォース", "problem_types": ["COINED_TERM"]},
        {"term_jp": "田中さん", "problem_types": ["HONORIFIC"]},
    ]
    results = classify_batch(terms)
    assert len(results) == 3
    assert results[0].grade == TermGrade.G1_UNIVERSAL
    assert results[1].grade == TermGrade.G6_COINED
    assert results[2].grade == TermGrade.G5_CULTURAL
