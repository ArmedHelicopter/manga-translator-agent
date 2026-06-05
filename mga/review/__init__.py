"""Review module — same-page and multi-page review workflows."""

from __future__ import annotations

from .diff import build_translation_diff, load_translation_candidates, write_translation_diff
from .report import (
    build_repair_plan_from_translation_report,
    build_review_reports_from_translation_report,
    compare_translations,
    generate_review_report,
    load_repair_plan_from_translation_report,
    load_review_reports_from_translation_report,
    write_repair_plan_artifact,
    write_review_artifacts,
)

__all__ = [
    "build_repair_plan_from_translation_report",
    "build_translation_diff",
    "build_review_reports_from_translation_report",
    "compare_translations",
    "generate_review_report",
    "load_repair_plan_from_translation_report",
    "load_review_reports_from_translation_report",
    "load_translation_candidates",
    "write_repair_plan_artifact",
    "write_translation_diff",
    "write_review_artifacts",
]
