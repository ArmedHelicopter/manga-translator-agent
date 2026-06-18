"""Lazy provider registry — discover provider metadata via AST scanning.

This module provides a metadata discovery layer that scans provider modules
for PROVIDER_METADATA dicts without importing them. This allows listing
provider capabilities (vision, structured, notes) without the import cost
of loading every provider class (and its SDK dependencies).

The canonical class-loading path remains _PROVIDER_MAP in factory.py
(get_provider/create_provider). This registry is a metadata source for
introspection (list_all_providers, get_provider_info, CLI listing).

Provider modules MAY declare a module-level PROVIDER_METADATA dict:

    PROVIDER_METADATA = {
        "name": "openai",
        "class": "OpenAIProvider",
        "vision": True,
        "structured": "json_mode",
        "notes": "Default primary provider",
    }

If absent, the registry falls back to _PROVIDER_MAP for the name/class and
reports unknown vision/structured (None).
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PROVIDERS_PACKAGE_DIR = Path(__file__).resolve().parent


@dataclass
class ProviderSpec:
    """Metadata for a provider discovered via AST scanning."""

    name: str
    module: str  # relative module path, e.g. ".openai_provider"
    class_name: str
    vision: Optional[bool] = None
    structured: Optional[str] = None
    notes: Optional[str] = None


def _extract_metadata(tree: ast.AST, module_stem: str) -> Optional[ProviderSpec]:
    """Extract PROVIDER_METADATA from a parsed module AST.

    Returns None if the module has no PROVIDER_METADATA assignment.
    """
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not (isinstance(target, ast.Name) and target.id == "PROVIDER_METADATA"):
                continue
            metadata = _eval_metadata_dict(node.value, module_stem)
            if metadata is not None:
                return metadata
    return None


def _eval_metadata_dict(node: ast.AST, module_stem: str) -> Optional[ProviderSpec]:
    """Evaluate a PROVIDER_METADATA dict literal into a ProviderSpec.

    Only handles dict literals with str keys and str/bool/None values.
    """
    if not isinstance(node, ast.Dict):
        return None
    raw: dict[str, Any] = {}
    for key_node, value_node in zip(node.keys, node.values):
        if not isinstance(key_node, ast.Constant):
            continue
        key = key_node.value
        raw[key] = _eval_literal(value_node)
    if "name" not in raw or "class" not in raw:
        return None
    return ProviderSpec(
        name=str(raw["name"]),
        module=module_stem,
        class_name=str(raw["class"]),
        vision=raw.get("vision") if isinstance(raw.get("vision"), bool) else None,
        structured=str(raw["structured"]) if raw.get("structured") else None,
        notes=str(raw["notes"]) if raw.get("notes") else None,
    )


def _eval_literal(node: ast.AST) -> Any:
    """Evaluate a simple literal node (str, bool, None) to its value."""
    if isinstance(node, ast.Constant):
        return node.value
    return None


def scan_provider_metadata(package_dir: Path | None = None) -> dict[str, ProviderSpec]:
    """Scan *_provider.py files for PROVIDER_METADATA without importing.

    Args:
        package_dir: Directory to scan. Defaults to the mga/providers/ directory.

    Returns:
        Dict mapping provider name → ProviderSpec. Modules without
        PROVIDER_METADATA are omitted (fall back to _PROVIDER_MAP for those).
    """
    scan_dir = package_dir or _PROVIDERS_PACKAGE_DIR
    specs: dict[str, ProviderSpec] = {}
    for path in sorted(scan_dir.glob("*_provider.py")):
        module_stem = f".{path.stem}"
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            logger.debug("Skipping provider module with syntax error: %s", path)
            continue
        spec = _extract_metadata(tree, module_stem)
        if spec is not None:
            specs[spec.name] = spec
    return specs


@lru_cache(maxsize=1)
def get_provider_specs() -> dict[str, ProviderSpec]:
    """Cached provider specs from AST scan + _PROVIDER_MAP fallback.

    Merges:
    1. _PROVIDER_MAP entries (name → (module, class)) as base specs
    2. PROVIDER_METADATA from AST scan (overrides with vision/structured/notes)

    This ensures every _PROVIDER_MAP entry is represented even if its module
    has no PROVIDER_METADATA dict.
    """
    # Start with _PROVIDER_MAP as the base (name → module/class).
    from .factory import _PROVIDER_MAP

    specs: dict[str, ProviderSpec] = {}
    for name, (module, class_name) in _PROVIDER_MAP.items():
        specs[name] = ProviderSpec(
            name=name, module=module, class_name=class_name,
            vision=None, structured=None, notes=None,
        )

    # Override/augment with AST-scanned metadata.
    for name, spec in scan_provider_metadata().items():
        if name in specs:
            # Merge: AST provides vision/structured/notes, base provides module/class.
            specs[name].vision = spec.vision
            specs[name].structured = spec.structured
            specs[name].notes = spec.notes
        else:
            specs[name] = spec

    return specs


def list_lazy_providers() -> list[str]:
    """List all provider names discovered via lazy registry (no imports)."""
    return sorted(get_provider_specs().keys())


def get_lazy_provider_info(name: str) -> Optional[dict[str, Any]]:
    """Get provider metadata without importing the provider module.

    Returns:
        Dict with keys: name, module, class, vision, structured, notes.
        None if provider not found.
    """
    spec = get_provider_specs().get(name.lower())
    if spec is None:
        return None
    return {
        "name": spec.name,
        "module": spec.module,
        "class": spec.class_name,
        "vision": spec.vision,
        "structured": spec.structured,
        "notes": spec.notes,
    }
