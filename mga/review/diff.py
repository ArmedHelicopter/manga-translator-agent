"""Translation diff loading and artifact writing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mga.artifacts import ArtifactStore
from mga.models import TranslationCandidate

from .report import compare_translations


@dataclass
class _TranslationDiffRecord:
    bubble_id: str = ""
    text: str = ""
    page_id: str = ""
    source_text: str = ""
    speaker_id: str | None = None
    confidence: float | None = None
    needs_human_review: bool | None = None
    qa_findings: list[dict[str, Any]] = field(default_factory=list)
    repair_plan: list[dict[str, Any]] = field(default_factory=list)


def _candidate_from_report_entry(entry: dict[str, Any]) -> TranslationCandidate:
    payload = dict(entry)
    if "text" not in payload and "translated_text" in payload:
        payload["text"] = payload["translated_text"]
    return TranslationCandidate.model_validate(payload)


def _record_from_candidate(candidate: TranslationCandidate) -> _TranslationDiffRecord:
    return _TranslationDiffRecord(
        bubble_id=candidate.bubble_id,
        text=candidate.text,
        confidence=candidate.confidence,
    )


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _record_from_report_entry(entry: dict[str, Any]) -> _TranslationDiffRecord:
    return _TranslationDiffRecord(
        bubble_id=str(entry.get("bubble_id", "")),
        text=str(entry.get("translated_text", entry.get("text", ""))),
        page_id=str(entry.get("page_id", "")),
        source_text=str(entry.get("source_text", "")),
        speaker_id=(
            str(entry["speaker_id"])
            if entry.get("speaker_id") is not None
            else None
        ),
        confidence=_optional_float(entry.get("confidence")),
        needs_human_review=(
            bool(entry["needs_human_review"])
            if "needs_human_review" in entry
            else None
        ),
        qa_findings=_dict_items(entry.get("qa_findings")),
        repair_plan=_dict_items(entry.get("repair_plan")),
    )


def _load_translation_payload(path: str | Path) -> tuple[list[Any], bool]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    from_report_entries = False
    if isinstance(payload, dict):
        if "entries" in payload:
            payload = payload["entries"]
            from_report_entries = True
        else:
            for key in ("translations", "candidates"):
                if key in payload:
                    payload = payload[key]
                    break

    if not isinstance(payload, list):
        raise ValueError(
            "translation diff input must be a JSON list or contain a translations/candidates/entries list"
        )
    return payload, from_report_entries


def load_translation_candidates(path: str | Path) -> list[TranslationCandidate]:
    """Load translation candidates from a JSON list or wrapped payload."""
    payload, from_report_entries = _load_translation_payload(path)

    if from_report_entries:
        if not all(isinstance(item, dict) for item in payload):
            raise ValueError("translation report entries must be JSON objects")
        return [_candidate_from_report_entry(item) for item in payload]

    return [TranslationCandidate.model_validate(item) for item in payload]


def _load_translation_diff_records(path: str | Path) -> list[_TranslationDiffRecord]:
    payload, from_report_entries = _load_translation_payload(path)
    if from_report_entries:
        if not all(isinstance(item, dict) for item in payload):
            raise ValueError("translation report entries must be JSON objects")
        return [_record_from_report_entry(item) for item in payload]
    return [
        _record_from_candidate(TranslationCandidate.model_validate(item))
        for item in payload
    ]


def _change_context(
    original: _TranslationDiffRecord | None,
    revised: _TranslationDiffRecord | None,
) -> dict[str, Any]:
    context: dict[str, Any] = {}
    primary = revised or original
    fallback = original if revised is not original else None
    if primary is None:
        return context

    page_id = primary.page_id or (fallback.page_id if fallback else "")
    if page_id:
        context["page_id"] = page_id
    source_text = primary.source_text or (fallback.source_text if fallback else "")
    if source_text:
        context["source_text"] = source_text
    speaker_id = primary.speaker_id or (fallback.speaker_id if fallback else None)
    if speaker_id:
        context["speaker_id"] = speaker_id
    if original and original.confidence is not None:
        context["original_confidence"] = original.confidence
    if revised and revised.confidence is not None:
        context["revised_confidence"] = revised.confidence
    needs_review = any(
        record.needs_human_review is True
        for record in (original, revised)
        if record is not None
    )
    if needs_review:
        context["needs_human_review"] = True
    qa_findings = primary.qa_findings or (fallback.qa_findings if fallback else [])
    if qa_findings:
        context["qa_findings"] = qa_findings
    repair_plan = primary.repair_plan or (fallback.repair_plan if fallback else [])
    if repair_plan:
        context["repair_plan"] = repair_plan
    return context


def _compare_translation_records(
    original: list[_TranslationDiffRecord],
    revised: list[_TranslationDiffRecord],
) -> dict[str, Any]:
    orig_map = {record.bubble_id: record for record in original}
    rev_map = {record.bubble_id: record for record in revised}

    all_ids = list(dict.fromkeys(list(orig_map) + list(rev_map)))
    changes: list[dict[str, Any]] = []
    for bubble_id in all_ids:
        original_record = orig_map.get(bubble_id)
        revised_record = rev_map.get(bubble_id)
        old = original_record.text if original_record else ""
        new = revised_record.text if revised_record else ""
        if old == new:
            continue
        if bubble_id not in orig_map:
            change_type = "added"
        elif bubble_id not in rev_map:
            change_type = "removed"
        else:
            change_type = "changed"
        diff_lines = compare_translations(
            [TranslationCandidate(bubble_id=bubble_id, text=old)],
            [TranslationCandidate(bubble_id=bubble_id, text=new)],
        )["changes"][0]["diff"]
        changes.append({
            "bubble_id": bubble_id,
            "change_type": change_type,
            "original": old,
            "revised": new,
            "diff": diff_lines,
            **_change_context(original_record, revised_record),
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


def build_translation_diff(original_path: str | Path, revised_path: str | Path) -> dict[str, Any]:
    """Build a structured diff between two translation JSON artifacts."""
    return _compare_translation_records(
        _load_translation_diff_records(original_path),
        _load_translation_diff_records(revised_path),
    )


def write_translation_diff(
    original_path: str | Path,
    revised_path: str | Path,
    output_path: str | Path,
) -> tuple[str, dict[str, Any]]:
    """Write review/diff.json under output_path and return its relative path and payload."""
    payload = build_translation_diff(original_path, revised_path)
    artifact_path = ArtifactStore(Path(output_path)).write_json("review/diff.json", payload)
    return artifact_path, payload
