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


_TERM_FIELD_ALIASES = {
    "term_jp",
    "term_target",
    "zh",
    "target",
    "candidate_translations",
    "reading",
    "problem_types",
    "type",
    "strategy",
    "notes",
    "accepted_reason",
    "rejected_reasons",
    "applicability_scope",
    "confirmed",
    "pending_human_review",
}


@dataclass
class TermState:
    """A single terminology entry with translation state."""
    term_jp: str
    term_target: str = ""
    candidate_translations: list[str] = field(default_factory=list)
    reading: str = ""
    problem_types: list[str] = field(default_factory=list)
    strategy: str = ""
    notes: str = ""
    accepted_reason: str = ""
    rejected_reasons: dict[str, str] = field(default_factory=dict)
    applicability_scope: str = ""
    confirmed: bool = False
    pending_human_review: bool = False

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


def _looks_like_term_entry(entry: dict[str, Any]) -> bool:
    return any(key in entry for key in _TERM_FIELD_ALIASES)


def _iter_term_entries(data: dict[str, Any]) -> list[tuple[str | None, str, dict[str, Any]]]:
    terms_section = data.get("terms")
    if isinstance(terms_section, dict):
        return [
            (None, key, entry)
            for key, entry in terms_section.items()
            if isinstance(entry, dict)
        ]

    entries: list[tuple[str | None, str, dict[str, Any]]] = []
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        if _looks_like_term_entry(value):
            entries.append((None, key, value))
            continue
        for term_key, term_entry in value.items():
            if isinstance(term_entry, dict):
                entries.append((key, term_key, term_entry))
    return entries


def _coerce_problem_types(
    raw: Any,
    *,
    category: str | None,
    type_alias: Any,
) -> list[str]:
    if isinstance(raw, str):
        problem_types = [raw]
    elif isinstance(raw, list):
        problem_types = [str(item) for item in raw if str(item)]
    else:
        problem_types = []

    for value in (category, type_alias):
        if value and str(value) not in problem_types:
            problem_types.append(str(value))
    return problem_types


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
        for category, key, entry in _iter_term_entries(data):
            jp = entry.get("term_jp", key)
            self._terms[jp] = TermState(
                term_jp=jp,
                term_target=entry.get("term_target", entry.get("zh", entry.get("target", ""))),
                candidate_translations=entry.get("candidate_translations", []),
                reading=entry.get("reading", ""),
                problem_types=_coerce_problem_types(
                    entry.get("problem_types", []),
                    category=category,
                    type_alias=entry.get("type"),
                ),
                strategy=entry.get("strategy", ""),
                notes=entry.get("notes", ""),
                accepted_reason=entry.get("accepted_reason", ""),
                rejected_reasons=entry.get("rejected_reasons", {}),
                applicability_scope=entry.get("applicability_scope", ""),
                confirmed=entry.get("confirmed", False),
                pending_human_review=entry.get("pending_human_review", False),
            )

    def lookup(self, term_jp: str) -> TermState | None:
        return self._terms.get(term_jp)

    def register(self, term: TermState) -> None:
        self._terms[term.term_jp] = term

    def items(self) -> list[TermState]:
        """Return terminology entries in stable key order."""
        return [self._terms[key] for key in sorted(self._terms)]

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
            if st.problem_types:
                parts.append(f"types={', '.join(st.problem_types)}")
            if st.strategy:
                parts.append(f"[{st.strategy}]")
            if st.notes:
                parts.append(f"-- {st.notes}")
            if st.candidate_translations:
                parts.append(f"candidates={', '.join(st.candidate_translations)}")
            if st.accepted_reason:
                parts.append(f"accepted_reason={st.accepted_reason}")
            if st.rejected_reasons:
                rejected = "; ".join(
                    f"{candidate}: {reason}"
                    for candidate, reason in st.rejected_reasons.items()
                )
                parts.append(f"rejected={rejected}")
            if st.applicability_scope:
                parts.append(f"scope={st.applicability_scope}")
            lines.append(" ".join(parts))
        return "" if len(lines) <= 2 else "\n".join(lines) + "\n"

    @property
    def size(self) -> int:
        return len(self._terms)
