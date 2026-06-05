"""Load project-level fictional script mapping assets."""

from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]


def load_fictional_script_context(project_dir: Path) -> dict[str, dict[str, Any]]:
    """Load `fictional_scripts/*.toml` into a prompt/QA-friendly context."""
    scripts_dir = project_dir / "fictional_scripts"
    if not scripts_dir.exists():
        return {}

    context: dict[str, dict[str, Any]] = {}
    for path in sorted(scripts_dir.rglob("*.toml")):
        try:
            payload = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        meta = payload.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}
        mapping = payload.get("mapping", {})
        if not isinstance(mapping, dict):
            mapping = {}
        notes = payload.get("notes", {})
        if not isinstance(notes, dict):
            notes = {}

        context[path.stem] = {
            "name": str(meta.get("name", path.stem)),
            "source": str(meta.get("source", "")),
            "has_mapping": bool(meta.get("has_mapping", bool(mapping))),
            "mapping": {str(key): str(value) for key, value in mapping.items()},
            "notes": {str(key): str(value) for key, value in notes.items()},
        }
    return context
