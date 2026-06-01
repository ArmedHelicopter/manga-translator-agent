"""Unified translation report — associates translations with pages and QA findings."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from ..pipeline.stages import PipelineContext


@dataclass
class TranslationEntry:
    """A single translation with full context —原文/译文/QA/cultural."""
    bubble_id: str
    page_id: str
    source_text: str
    translated_text: str
    confidence: float
    rationale: str
    qa_findings: list[dict[str, Any]] = field(default_factory=list)
    cultural_strategy: str | None = None
    needs_human_review: bool = False
    speaker_id: str | None = None
    semantic_text: str | None = None
    semantic_rationale: str | None = None
    persona_moves: list[str] = field(default_factory=list)
    persona_rationale: str | None = None
    provider_trace: dict[str, Any] = field(default_factory=dict)
    provider_cascade_errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class TranslationReport:
    """Full translation report — one entry per translated bubble."""
    entries: list[TranslationEntry] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def _bubble_to_page_map(ctx: PipelineContext) -> dict[str, str]:
    """Build bubble_id → page_id mapping from pages."""
    mapping: dict[str, str] = {}
    for page in ctx.pages:
        for bubble in page.bubbles:
            mapping[bubble.bubble_id] = page.page_id
    return mapping


def _qa_findings_by_bubble(ctx: PipelineContext) -> dict[str, list[dict]]:
    """Group QA findings by bubble_id."""
    result: dict[str, list[dict]] = {}
    qa = ctx.qa_report
    if not qa:
        return result

    # QA report can have "findings" or "per_page" keys
    findings = qa.get("findings", [])
    if not findings and "per_page" in qa:
        for page_findings in qa["per_page"].values():
            findings.extend(page_findings)

    for finding in findings:
        bid = finding.get("bubble_id", "")
        if bid:
            result.setdefault(bid, []).append(finding)
    return result


def _dialogue_realization_by_bubble(ctx: PipelineContext) -> dict[str, dict]:
    trace = ctx.artifacts.get("translation", {}).get("dialogue_realization", {})
    entries = trace.get("entries", []) if isinstance(trace, dict) else []
    return {
        entry.get("bubble_id", ""): entry
        for entry in entries
        if isinstance(entry, dict) and entry.get("bubble_id")
    }


def _provider_errors_by_bubble(ctx: PipelineContext) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    errors = ctx.artifacts.get("translation", {}).get("provider_cascade_errors", [])
    for error in errors if isinstance(errors, list) else []:
        if not isinstance(error, dict):
            continue
        bubble_id = error.get("bubble_id")
        if bubble_id:
            result.setdefault(str(bubble_id), []).append(error)
    return result


def build_translation_report(ctx: PipelineContext) -> TranslationReport:
    """Build a translation report from PipelineContext."""
    b2p = _bubble_to_page_map(ctx)
    qa_by_bubble = _qa_findings_by_bubble(ctx)
    realization_by_bubble = _dialogue_realization_by_bubble(ctx)
    provider_errors_by_bubble = _provider_errors_by_bubble(ctx)

    entries: list[TranslationEntry] = []
    for t in ctx.translations:
        page_id = b2p.get(t.bubble_id, "")
        qa = qa_by_bubble.get(t.bubble_id, [])
        needs_review = t.confidence < 0.7 or any(
            f.get("severity") == "critical" for f in qa
        )
        realization = realization_by_bubble.get(t.bubble_id, {})
        semantic = realization.get("semantic", {}) if isinstance(realization, dict) else {}
        persona = realization.get("persona", {}) if isinstance(realization, dict) else {}
        entries.append(TranslationEntry(
            bubble_id=t.bubble_id,
            page_id=page_id,
            source_text="",  # Will be filled if available in page bubbles
            translated_text=t.text,
            confidence=t.confidence,
            rationale=t.rationale,
            qa_findings=qa,
            needs_human_review=needs_review,
            speaker_id=realization.get("speaker_id") if isinstance(realization, dict) else None,
            semantic_text=semantic.get("text") if isinstance(semantic, dict) else None,
            semantic_rationale=semantic.get("rationale") if isinstance(semantic, dict) else None,
            persona_moves=persona.get("persona_moves", []) if isinstance(persona, dict) else [],
            persona_rationale=persona.get("rationale") if isinstance(persona, dict) else None,
            provider_trace=realization.get("provider", {}) if isinstance(realization, dict) else {},
            provider_cascade_errors=provider_errors_by_bubble.get(t.bubble_id, []),
        ))

    # Fill source_text from pages
    for page in ctx.pages:
        for bubble in page.bubbles:
            for entry in entries:
                if entry.bubble_id == bubble.bubble_id:
                    entry.source_text = bubble.source_text

    # Summary stats
    total = len(entries)
    avg_conf = sum(e.confidence for e in entries) / total if total else 0.0
    review_pages = {e.page_id for e in entries if e.needs_human_review and e.page_id}
    provider_error_count = sum(len(e.provider_cascade_errors) for e in entries)

    summary = {
        "total_translations": total,
        "avg_confidence": round(avg_conf, 3),
        "pages_needing_human_review": len(review_pages),
        "entries_needing_human_review": sum(1 for e in entries if e.needs_human_review),
        "qa_findings_total": sum(len(e.qa_findings) for e in entries),
        "provider_cascade_errors_total": provider_error_count,
    }

    return TranslationReport(entries=entries, summary=summary)


def write_translation_report(store: Any, report: TranslationReport) -> str:
    """Write translation report to store. Returns relative path."""
    payload = {
        "entries": [asdict(e) for e in report.entries],
        "summary": report.summary,
    }
    return store.write_translation_report(payload)
