"""Compatibility shim for mga.format.manifest utilities."""

from mga.format.manifest import *  # noqa: F401,F403
from mga.format.manifest import (  # explicit re-exports
    build_manifest_payload,
    discover_image_paths,
    load_image_metadata,
)

__all__ = [
    "build_manifest_payload",
    "discover_image_paths",
    "load_image_metadata",
]
