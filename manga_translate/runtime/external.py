"""Compatibility shim for mga.runtime_bridge.external."""

from mga.runtime_bridge.external import *  # noqa: F401,F403
from mga.runtime_bridge.external import (  # explicit re-exports
    _build_external_child_env,
    _normalize_external_text_blocks,
    _parse_saved_text_blocks,
    resolve_external_runtime_repo,
    run_external_translation_runtime,
)

__all__ = [
    "_build_external_child_env",
    "_normalize_external_text_blocks",
    "_parse_saved_text_blocks",
    "resolve_external_runtime_repo",
    "run_external_translation_runtime",
]
