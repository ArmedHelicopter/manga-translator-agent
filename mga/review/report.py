"""Review report generation and artifact persistence."""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from pathlib import Path
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


def _feedback_severity(feedback: dict[str, Any]) -> str:
    severity = str(feedback.get("severity", "")).lower()
    if severity:
        return severity

    feedback_type = str(feedback.get("feedback_type", "")).lower()
    return {
        "error": "critical",
        "warning": "warning",
        "suggestion": "info",
    }.get(feedback_type, "info")


def _feedback_needs_human_review(feedback: dict[str, Any]) -> bool:
    if _feedback_severity(feedback) == "critical":
        return True
    try:
        confidence = float(feedback.get("confidence", 1.0))
    except (TypeError, ValueError):
        confidence = 1.0
    return confidence < 0.7


def _aggregate_score(feedbacks: list[dict[str, Any]]) -> float:
    """Derive a 0-1 score from QA feedback severity counts."""
    if not feedbacks:
        return 1.0
    severity_weights = {"critical": 0.3, "warning": 0.15, "info": 0.05}
    penalty = sum(severity_weights.get(_feedback_severity(f), 0.05) for f in feedbacks)
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
        _feedback_needs_human_review(f) for f in feedbacks
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


def build_review_reports_from_translation_report(payload: dict[str, Any]) -> list[ReviewReport]:
    """Build page-level review reports from a translation-report.json payload."""
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("translation report must contain an entries list")

    by_page: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("translation report entries must be JSON objects")
        page_id = str(entry.get("page_id") or "unknown")
        by_page.setdefault(page_id, []).append(entry)

    reports: list[ReviewReport] = []
    for page_id, page_entries in by_page.items():
        qa_feedbacks = [
            finding
            for entry in page_entries
            for finding in entry.get("qa_findings", [])
            if isinstance(finding, dict)
        ]
        source_text = "\n".join(
            str(entry.get("source_text", "")) for entry in page_entries
        )
        translation_text = "\n".join(
            str(entry.get("translated_text", entry.get("text", "")))
            for entry in page_entries
        )
        score = _aggregate_score(qa_feedbacks)
        needs_human = any(
            bool(entry.get("needs_human_review")) for entry in page_entries
        ) or score < 0.7 or any(
            _feedback_needs_human_review(finding) for finding in qa_feedbacks
        )
        reports.append(
            ReviewReport(
                page_id=page_id,
                source_text=source_text,
                translation_text=translation_text,
                qa_feedbacks=qa_feedbacks,
                score=score,
                needs_human_review=needs_human,
            )
        )

    return reports


def load_review_reports_from_translation_report(path: str | Path) -> list[ReviewReport]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("translation report must be a JSON object")
    return build_review_reports_from_translation_report(payload)


def build_repair_plan_from_translation_report(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten entry-level repair plans from a translation-report.json payload."""
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise ValueError("translation report must contain an entries list")

    repairs: list[dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("translation report entries must be JSON objects")
        entry_repairs = entry.get("repair_plan", [])
        if not isinstance(entry_repairs, list):
            continue
        for item in entry_repairs:
            if not isinstance(item, dict):
                continue
            repair = dict(item)
            repair.setdefault("bubble_id", entry.get("bubble_id", ""))
            repair.setdefault("page_id", entry.get("page_id", ""))
            repairs.append(repair)

    targets: dict[str, int] = {}
    actions: dict[str, int] = {}
    for repair in repairs:
        target = str(repair.get("target", "unknown") or "unknown")
        action = str(repair.get("action", "unknown") or "unknown")
        targets[target] = targets.get(target, 0) + 1
        actions[action] = actions.get(action, 0) + 1

    return {
        "repairs": repairs,
        "summary": {
            "total_repairs": len(repairs),
            "targets": targets,
            "actions": actions,
        },
    }


def load_repair_plan_from_translation_report(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("translation report must be a JSON object")
    return build_repair_plan_from_translation_report(payload)


def write_repair_plan_artifact(store: ArtifactStore, payload: dict[str, Any]) -> str:
    """Persist a flattened repair plan as JSON via ArtifactStore."""
    return store.write_json("review/repair-plan.json", payload)


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
            if bid not in orig_map:
                change_type = "added"
            elif bid not in rev_map:
                change_type = "removed"
            else:
                change_type = "changed"
            diff_lines = list(difflib.unified_diff(
                old.splitlines(), new.splitlines(),
                fromfile=f"original/{bid}", tofile=f"revised/{bid}",
                lineterm="",
            ))
            changes.append({
                "bubble_id": bid,
                "change_type": change_type,
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
