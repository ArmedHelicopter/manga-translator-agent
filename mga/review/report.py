"""Review report generation and artifact persistence."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any

from mga.artifacts import ArtifactStore
from mga.models import TranslationCandidate


@dataclass
class ReviewReport:
    """Structured review result for a single page."""

    page_id: str
    source_text: str
    translation_text: str
    qa_feedbacks: list[dict[str, Any]] = field(default_factory=list)
    score: float = 0.0
    needs_human_review: bool = False


def _aggregate_score(feedbacks: list[dict[str, Any]]) -> float:
    """Derive a 0-1 score from QA feedback severity counts."""
    if not feedbacks:
        return 1.0
    severity_weights = {"critical": 0.3, "warning": 0.15, "info": 0.05}
    penalty = sum(severity_weights.get(f.get("severity", "info"), 0.05) for f in feedbacks)
    return max(0.0, 1.0 - penalty)


def generate_review_report(
    translations: list[TranslationCandidate],
    qa_report: dict,
    context: dict,
) -> ReviewReport:
    """Build a ReviewReport from translations, QA findings, and page context."""
    page_id = context.get("page_id", "unknown")
    source_text = "\n".join(
        context.get("source_texts", [t.rationale for t in translations])
    )
    translation_text = "\n".join(t.text for t in translations)

    feedbacks: list[dict[str, Any]] = []
    if "findings" in qa_report:
        feedbacks = list(qa_report["findings"])
    elif "feedbacks" in qa_report:
        feedbacks = list(qa_report["feedbacks"])

    score = _aggregate_score(feedbacks)
    needs_human = score < 0.7 or any(
        f.get("severity") == "critical" for f in feedbacks
    )

    return ReviewReport(
        page_id=page_id,
        source_text=source_text,
        translation_text=translation_text,
        qa_feedbacks=feedbacks,
        score=score,
        needs_human_review=needs_human,
    )


def write_review_artifacts(
    store: ArtifactStore,
    reports: list[ReviewReport],
) -> str:
    """Persist review reports as JSON via ArtifactStore. Returns relative path."""
    payload = {
        "reports": [r.__dict__ for r in reports],
        "summary": {
            "total_pages": len(reports),
            "avg_score": (
                round(sum(r.score for r in reports) / len(reports), 3)
                if reports
                else 0.0
            ),
            "pages_needing_human_review": sum(
                1 for r in reports if r.needs_human_review
            ),
        },
    }
    return store.write_json("review/report.json", payload)


def compare_translations(
    original: list[TranslationCandidate],
    revised: list[TranslationCandidate],
) -> dict:
    """Diff two translation lists and return a structured change report."""
    orig_map = {t.bubble_id: t.text for t in original}
    rev_map = {t.bubble_id: t.text for t in revised}

    all_ids = list(dict.fromkeys(list(orig_map) + list(rev_map)))
    changes: list[dict[str, Any]] = []
    for bid in all_ids:
        old = orig_map.get(bid, "")
        new = rev_map.get(bid, "")
        if old != new:
            diff_lines = list(difflib.unified_diff(
                old.splitlines(), new.splitlines(),
                fromfile=f"original/{bid}", tofile=f"revised/{bid}",
                lineterm="",
            ))
            changes.append({
                "bubble_id": bid,
                "original": old,
                "revised": new,
                "diff": diff_lines,
            })

    total_bubbles = len(all_ids)
    return {
        "total_bubbles": total_bubbles,
        "changed_bubbles": len(changes),
        "change_ratio": (
            round(len(changes) / total_bubbles, 3) if total_bubbles else 0.0
        ),
        "changes": changes,
    }
