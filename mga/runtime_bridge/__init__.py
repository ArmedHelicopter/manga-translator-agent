"""Bridges from the host layer into the external runtime."""

from .external import resolve_external_runtime_repo, run_external_translation_runtime

__all__ = ["resolve_external_runtime_repo", "run_external_translation_runtime"]
