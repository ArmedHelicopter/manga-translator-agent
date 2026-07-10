"""Artifact store and report generation."""

from .store import ArtifactStore

__all__ = [
    "ArtifactStore",
    "RunSummary",
    "build_run_summary",
    "write_run_summary",
    "TranslationEntry",
    "TranslationReport",
    "build_translation_report",
    "write_translation_report",
]


def __getattr__(name: str):
    """Lazy imports to avoid circular dependency with mga.pipeline."""
    if name in ("RunSummary", "build_run_summary", "write_run_summary"):
        from .run_summary import RunSummary, build_run_summary, write_run_summary
        return {"RunSummary": RunSummary, "build_run_summary": build_run_summary, "write_run_summary": write_run_summary}[name]
    if name in ("TranslationEntry", "TranslationReport", "build_translation_report", "write_translation_report"):
        from .translation_report import (
            TranslationEntry, TranslationReport, build_translation_report, write_translation_report,
        )
        return {
            "TranslationEntry": TranslationEntry,
            "TranslationReport": TranslationReport,
            "build_translation_report": build_translation_report,
            "write_translation_report": write_translation_report,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
