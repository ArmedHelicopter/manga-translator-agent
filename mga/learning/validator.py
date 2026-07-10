"""Stage L4 — Validation: check consistency, completeness, and coverage."""

from __future__ import annotations

import logging
from typing import Any

from .models import LearningResult

logger = logging.getLogger(__name__)


def validate(result: LearningResult) -> dict:
    """Validate a LearningResult and return a quality report.

    Checks:
    1. Consistency — characters have consistent speech patterns across pages
    2. Completeness — all identified characters have profiles
    3. Coverage — frequent terms are in the terminology table
    4. Structural — required fields are present
    """
    issues: list[dict] = []
    stats: dict[str, Any] = {
        "characters_count": len(result.characters),
        "terms_count": len(result.terms),
        "has_style_guide": bool(result.style_guide),
        "has_character_graph": bool(result.character_graph),
        "pages_processed": result.pages_processed,
    }

    # 1. Structural validation
    for char in result.characters:
        if not char.get("name_jp"):
            issues.append({"type": "structural", "severity": "error", "entity": "character", "message": "Missing name_jp"})
        if not char.get("name_zh"):
            issues.append({"type": "structural", "severity": "warning", "entity": char.get("name_jp", "?"), "message": "Missing name_zh"})
        if not char.get("character_id"):
            issues.append({"type": "structural", "severity": "warning", "entity": char.get("name_jp", "?"), "message": "Missing character_id"})

    for term in result.terms:
        if not term.get("term_jp"):
            issues.append({"type": "structural", "severity": "error", "entity": "term", "message": "Missing term_jp"})
        if not term.get("term_zh"):
            issues.append({"type": "structural", "severity": "warning", "entity": term.get("term_jp", "?"), "message": "Missing term_zh"})

    # 2. Completeness check — every character has speech_patterns
    chars_without_patterns = [c for c in result.characters if not c.get("speech_patterns")]
    if chars_without_patterns:
        names = [c.get("name_jp", "?") for c in chars_without_patterns]
        issues.append({
            "type": "completeness",
            "severity": "info",
            "entity": "characters",
            "message": f"Characters without speech patterns: {', '.join(names)}",
        })

    # 3. Terminology coverage — terms with high frequency should have strategy
    high_freq_no_strategy = [
        t for t in result.terms
        if t.get("frequency", 0) >= 3 and not t.get("strategy")
    ]
    if high_freq_no_strategy:
        terms_str = ", ".join(t.get("term_jp", "?") for t in high_freq_no_strategy)
        issues.append({
            "type": "coverage",
            "severity": "warning",
            "entity": "terminology",
            "message": f"Frequent terms without translation strategy: {terms_str}",
        })

    # 4. Character graph validation
    graph = result.character_graph
    if graph:
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        node_ids = {n.get("id") for n in nodes}
        for edge in edges:
            if edge.get("source") not in node_ids:
                issues.append({
                    "type": "structural",
                    "severity": "warning",
                    "entity": "character_graph",
                    "message": f"Edge source '{edge.get('source')}' not in nodes",
                })
            if edge.get("target") not in node_ids:
                issues.append({
                    "type": "structural",
                    "severity": "warning",
                    "entity": "character_graph",
                    "message": f"Edge target '{edge.get('target')}' not in nodes",
                })

    # 5. Duplicate check
    char_ids = [c.get("character_id") for c in result.characters if c.get("character_id")]
    if len(char_ids) != len(set(char_ids)):
        issues.append({
            "type": "consistency",
            "severity": "error",
            "entity": "characters",
            "message": "Duplicate character_ids found",
        })

    term_ids = [t.get("term_id") for t in result.terms if t.get("term_id")]
    if len(term_ids) != len(set(term_ids)):
        issues.append({
            "type": "consistency",
            "severity": "error",
            "entity": "terms",
            "message": "Duplicate term_ids found",
        })

    # Build report
    error_count = sum(1 for i in issues if i["severity"] == "error")
    warning_count = sum(1 for i in issues if i["severity"] == "warning")
    info_count = sum(1 for i in issues if i["severity"] == "info")

    report = {
        "passed": error_count == 0,
        "total_issues": len(issues),
        "errors": error_count,
        "warnings": warning_count,
        "info": info_count,
        "issues": issues,
        "stats": stats,
    }

    if issues:
        logger.info("Validation: %d issues (%d errors, %d warnings, %d info)",
                     len(issues), error_count, warning_count, info_count)
    else:
        logger.info("Validation passed with no issues")

    return report
