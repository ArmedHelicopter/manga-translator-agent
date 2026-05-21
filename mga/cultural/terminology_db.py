"""Per-work terminology database backed by TOML files."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

try:
    import tomli_w as _toml_writer  # type: ignore[import-untyped]
except ModuleNotFoundError:
    _toml_writer = None  # type: ignore[assignment]

from ..exceptions import ConfigError


@dataclass
class TermState:
    """A single terminology entry with translation state."""
    term_jp: str
    term_target: str = ""
    reading: str = ""
    problem_types: list[str] = field(default_factory=list)
    strategy: str = ""
    notes: str = ""
    confirmed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def _qkey(key: str) -> str:
    """Quote a key if it contains non-ASCII or special characters."""
    if all(c.isascii() and (c.isalnum() or c in "-_") for c in key):
        return key
    return f'"{key.replace(chr(92), chr(92)*2).replace(chr(34), chr(92)+chr(34))}"'


def _emit_val(value: Any, indent: int) -> str:
    """Emit a single TOML scalar or list value."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return f'"{value.replace(chr(92), chr(92)*2).replace(chr(34), chr(92)+chr(34))}"'
    if isinstance(value, list):
        return "[" + ", ".join(_emit_val(v, indent) for v in value) + "]"
    return f'"{value}"'


def _emit_dict(data: dict, prefix: str = "") -> str:
    """Emit a TOML document from a nested dict (fallback when tomli_w is absent)."""
    sections: list[str] = []
    scalars: list[str] = []
    for key, value in data.items():
        fk = f"{prefix}.{_qkey(key)}" if prefix else _qkey(key)
        if isinstance(value, dict):
            sections.append(f"[{fk}]\n{_emit_dict(value, fk)}")
        else:
            scalars.append(f"{_qkey(key)} = {_emit_val(value, 0)}")
    return "\n".join(scalars + sections)


class TerminologyDB:
    """Project-scoped terminology database loaded from ``terminology/*.toml``."""

    def __init__(self) -> None:
        self._terms: dict[str, TermState] = {}

    @classmethod
    def load(cls, project_dir: str | Path) -> TerminologyDB:
        """Load all ``*.toml`` files from ``<project_dir>/terminology/``."""
        db = cls()
        term_dir = Path(project_dir) / "terminology"
        if not term_dir.exists():
            return db
        for toml_path in sorted(term_dir.glob("*.toml")):
            db._load_file(toml_path)
        return db

    def _load_file(self, path: Path) -> None:
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ConfigError(f"Failed to parse terminology file {path}: {exc}") from exc
        terms_section = data.get("terms", data)
        if not isinstance(terms_section, dict):
            return
        for key, entry in terms_section.items():
            if not isinstance(entry, dict):
                continue
            jp = entry.get("term_jp", key)
            self._terms[jp] = TermState(
                term_jp=jp, term_target=entry.get("term_target", ""),
                reading=entry.get("reading", ""),
                problem_types=entry.get("problem_types", []),
                strategy=entry.get("strategy", ""),
                notes=entry.get("notes", ""),
                confirmed=entry.get("confirmed", False),
            )

    def lookup(self, term_jp: str) -> TermState | None:
        return self._terms.get(term_jp)

    def register(self, term: TermState) -> None:
        self._terms[term.term_jp] = term

    def export(self, project_dir: str | Path) -> Path:
        """Write the current database back to a single TOML file."""
        out = Path(project_dir) / "terminology"
        out.mkdir(parents=True, exist_ok=True)
        out_path = out / "terms.toml"
        payload = {"terms": {jp: st.to_dict() for jp, st in self._terms.items()}}
        if _toml_writer is not None:
            out_path.write_bytes(_toml_writer.dumps(payload).encode("utf-8"))
        else:
            out_path.write_text(_emit_dict(payload), encoding="utf-8")
        return out_path

    def get_injection_context(self, terms: list[str]) -> str:
        """Return a formatted context block for prompt injection."""
        lines: list[str] = ["## Terminology Context", ""]
        for term_jp in terms:
            st = self._terms.get(term_jp)
            if st is None:
                continue
            parts = [f"- **{st.term_jp}**"]
            if st.reading:
                parts.append(f"({st.reading})")
            if st.term_target:
                parts.append(f"-> {st.term_target}")
            if st.strategy:
                parts.append(f"[{st.strategy}]")
            if st.notes:
                parts.append(f"-- {st.notes}")
            lines.append(" ".join(parts))
        return "" if len(lines) <= 2 else "\n".join(lines) + "\n"

    @property
    def size(self) -> int:
        return len(self._terms)
