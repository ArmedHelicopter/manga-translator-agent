"""Tests for mga.learning.validator — validation logic (Stage L4)."""

from mga.learning.models import LearningResult
from mga.learning.validator import validate


def test_validate_empty_result():
    result = LearningResult()
    report = validate(result)

    assert report["passed"] is True
    assert report["total_issues"] == 0
    assert report["errors"] == 0
    assert report["warnings"] == 0
    assert report["info"] == 0
    assert report["issues"] == []
    assert report["stats"]["characters_count"] == 0
    assert report["stats"]["terms_count"] == 0
    assert report["stats"]["has_style_guide"] is False
    assert report["stats"]["has_character_graph"] is False
    assert report["stats"]["pages_processed"] == 0


def test_validate_valid_result():
    result = LearningResult(
        characters=[
            {
                "character_id": "taro",
                "name_jp": "太郎",
                "name_zh": "太郎",
                "speech_patterns": {"自称": "我"},
            },
        ],
        terms=[
            {
                "term_id": "bushido",
                "term_jp": "武士道",
                "term_zh": "武士道",
                "strategy": "直译",
                "frequency": 2,
            },
        ],
        style_guide={"literal_vs_free": 0.5},
        character_graph={
            "nodes": [{"id": "taro", "label": "太郎"}],
            "edges": [],
        },
        pages_processed=3,
    )
    report = validate(result)

    assert report["passed"] is True
    assert report["errors"] == 0
    assert report["stats"]["characters_count"] == 1
    assert report["stats"]["terms_count"] == 1
    assert report["stats"]["pages_processed"] == 3


def test_validate_missing_name_zh():
    result = LearningResult(
        characters=[
            {
                "character_id": "taro",
                "name_jp": "太郎",
            },
        ],
    )
    report = validate(result)

    assert report["passed"] is True  # warning only, no errors
    assert report["warnings"] >= 1
    messages = [i["message"] for i in report["issues"]]
    assert any("Missing name_zh" in m for m in messages)


def test_validate_missing_name_jp():
    result = LearningResult(
        characters=[
            {
                "character_id": "taro",
                "name_zh": "太郎",
            },
        ],
    )
    report = validate(result)

    assert report["passed"] is False  # error
    assert report["errors"] >= 1
    messages = [i["message"] for i in report["issues"]]
    assert any("Missing name_jp" in m for m in messages)


def test_validate_high_freq_no_strategy():
    result = LearningResult(
        terms=[
            {
                "term_id": "bushido",
                "term_jp": "武士道",
                "term_zh": "武士道",
                "frequency": 5,
                "strategy": "",
            },
        ],
    )
    report = validate(result)

    assert report["passed"] is True  # warning only
    assert report["warnings"] >= 1
    messages = [i["message"] for i in report["issues"]]
    assert any("Frequent terms without translation strategy" in m for m in messages)


def test_validate_duplicate_character_ids():
    result = LearningResult(
        characters=[
            {"character_id": "taro", "name_jp": "太郎", "name_zh": "太郎"},
            {"character_id": "taro", "name_jp": "太郎二", "name_zh": "太郎二"},
        ],
    )
    report = validate(result)

    assert report["passed"] is False
    assert report["errors"] >= 1
    messages = [i["message"] for i in report["issues"]]
    assert any("Duplicate character_ids" in m for m in messages)


def test_validate_duplicate_term_ids():
    result = LearningResult(
        terms=[
            {"term_id": "bushido", "term_jp": "武士道", "term_zh": "武士道"},
            {"term_id": "bushido", "term_jp": "武士道2", "term_zh": "武士道2"},
        ],
    )
    report = validate(result)

    assert report["passed"] is False
    assert report["errors"] >= 1
    messages = [i["message"] for i in report["issues"]]
    assert any("Duplicate term_ids" in m for m in messages)


def test_validate_graph_edges_missing_nodes():
    result = LearningResult(
        character_graph={
            "nodes": [{"id": "taro", "label": "太郎"}],
            "edges": [
                {"source": "taro", "target": "hanako", "relationship": "friend"},
            ],
        },
    )
    report = validate(result)

    assert report["passed"] is True  # warnings only
    assert report["warnings"] >= 1
    messages = [i["message"] for i in report["issues"]]
    assert any("Edge target" in m and "not in nodes" in m for m in messages)


def test_validate_characters_without_speech_patterns():
    result = LearningResult(
        characters=[
            {"character_id": "taro", "name_jp": "太郎", "name_zh": "太郎"},
        ],
    )
    report = validate(result)

    info_issues = [i for i in report["issues"] if i["severity"] == "info"]
    assert len(info_issues) >= 1
    messages = [i["message"] for i in info_issues]
    assert any("speech patterns" in m for m in messages)


def test_validate_stats_populated():
    result = LearningResult(
        characters=[{"character_id": "a", "name_jp": "A", "name_zh": "A"}],
        terms=[{"term_id": "t", "term_jp": "T", "term_zh": "T"}],
        style_guide={"literal_vs_free": 0.5},
        character_graph={"nodes": [], "edges": []},
        pages_processed=5,
    )
    report = validate(result)

    stats = report["stats"]
    assert stats["characters_count"] == 1
    assert stats["terms_count"] == 1
    assert stats["has_style_guide"] is True
    assert stats["has_character_graph"] is True
    assert stats["pages_processed"] == 5
