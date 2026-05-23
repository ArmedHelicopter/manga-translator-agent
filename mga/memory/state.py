"""StateManager: read/write memory state as structured JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import TypeAdapter

from mga.memory.entities import (
    CharacterState,
    DecisionState,
    MemoryIndex,
    SceneState,
    TermState,
)

T = TypeVar("T")

_MEMORY_DIR = Path("memory")
_STATE_DIR = _MEMORY_DIR / "state"

_INDEX_FILE = _STATE_DIR / "index.json"

_SUBDIRS: dict[str, str] = {
    "characters": "characters",
    "scenes": "scenes",
    "terms": "terms",
    "decisions": "decisions",
}


def _ensure_dirs(project_dir: Path) -> None:
    """Create the memory/state directory tree if missing."""
    for sub in _SUBDIRS.values():
        (project_dir / _STATE_DIR / sub).mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _entity_path(project_dir: Path, kind: str, entity_id: str) -> Path:
    return project_dir / _STATE_DIR / _SUBDIRS[kind] / f"{entity_id}.json"


def _load_entity(path: Path, model: type[T]) -> T | None:
    if not path.exists():
        return None
    data = _read_json(path)
    return TypeAdapter(model).validate_python(data)


def _save_entity(path: Path, model: T) -> None:
    _write_json(path, model.model_dump())


# ── public API ────────────────────────────────────────────────


class StateManager:
    """Load, save, and mutate the structured memory state."""

    @staticmethod
    def load(project_dir: Path) -> MemoryIndex:
        _ensure_dirs(project_dir)
        data = _read_json(project_dir / _INDEX_FILE)
        return MemoryIndex.model_validate(data)

    @staticmethod
    def save(project_dir: Path, index: MemoryIndex) -> None:
        _ensure_dirs(project_dir)
        index.last_updated = index.last_updated or __import__("datetime").datetime.now().isoformat()
        _write_json(project_dir / _INDEX_FILE, index.model_dump())

    # ── characters ──────────────────────────────────────────

    @staticmethod
    def list_characters(project_dir: Path) -> list[CharacterState]:
        _ensure_dirs(project_dir)
        d = project_dir / _STATE_DIR / "characters"
        return [
            c for f in sorted(d.glob("*.json"))
            if (c := _load_entity(f, CharacterState)) is not None
        ]

    @staticmethod
    def get_character(project_dir: Path, character_id: str) -> CharacterState | None:
        return _load_entity(
            _entity_path(project_dir, "characters", character_id),
            CharacterState,
        )

    @staticmethod
    def upsert_character(project_dir: Path, character: CharacterState) -> None:
        cid = character.character_id or character.name_jp.lower().replace(" ", "_")
        character.character_id = cid
        _save_entity(_entity_path(project_dir, "characters", cid), character)
        idx = StateManager.load(project_dir)
        idx.characters[cid] = character.name_jp or cid
        idx.last_updated = __import__("datetime").datetime.now().isoformat()
        StateManager.save(project_dir, idx)

    # ── scenes ──────────────────────────────────────────────

    @staticmethod
    def list_scenes(project_dir: Path) -> list[SceneState]:
        _ensure_dirs(project_dir)
        d = project_dir / _STATE_DIR / "scenes"
        return [
            s for f in sorted(d.glob("*.json"))
            if (s := _load_entity(f, SceneState)) is not None
        ]

    @staticmethod
    def get_scene(project_dir: Path, scene_id: str) -> SceneState | None:
        return _load_entity(
            _entity_path(project_dir, "scenes", scene_id),
            SceneState,
        )

    @staticmethod
    def upsert_scene(project_dir: Path, scene: SceneState) -> None:
        sid = scene.scene_id or f"ch{scene.chapter}_p{scene.page}"
        scene.scene_id = sid
        _save_entity(_entity_path(project_dir, "scenes", sid), scene)
        idx = StateManager.load(project_dir)
        idx.scenes[sid] = sid
        idx.last_updated = __import__("datetime").datetime.now().isoformat()
        StateManager.save(project_dir, idx)

    # ── terms ───────────────────────────────────────────────

    @staticmethod
    def list_terms(project_dir: Path) -> list[TermState]:
        _ensure_dirs(project_dir)
        d = project_dir / _STATE_DIR / "terms"
        return [
            t for f in sorted(d.glob("*.json"))
            if (t := _load_entity(f, TermState)) is not None
        ]

    @staticmethod
    def get_term(project_dir: Path, term_id: str) -> TermState | None:
        return _load_entity(
            _entity_path(project_dir, "terms", term_id),
            TermState,
        )

    @staticmethod
    def upsert_term(project_dir: Path, term: TermState) -> None:
        tid = term.term_id or term.term_jp.lower().replace(" ", "_")
        term.term_id = tid
        _save_entity(_entity_path(project_dir, "terms", tid), term)
        idx = StateManager.load(project_dir)
        idx.terms[tid] = term.term_jp or tid
        idx.last_updated = __import__("datetime").datetime.now().isoformat()
        StateManager.save(project_dir, idx)

    # ── decisions ───────────────────────────────────────────

    @staticmethod
    def list_decisions(project_dir: Path) -> list[DecisionState]:
        _ensure_dirs(project_dir)
        d = project_dir / _STATE_DIR / "decisions"
        return [
            dec for f in sorted(d.glob("*.json"))
            if (dec := _load_entity(f, DecisionState)) is not None
        ]

    @staticmethod
    def get_decision(project_dir: Path, decision_id: str) -> DecisionState | None:
        return _load_entity(
            _entity_path(project_dir, "decisions", decision_id),
            DecisionState,
        )

    @staticmethod
    def upsert_decision(project_dir: Path, decision: DecisionState) -> None:
        did = decision.decision_id or f"dec_{decision.stage}_{decision.timestamp[:10]}"
        decision.decision_id = did
        _save_entity(_entity_path(project_dir, "decisions", did), decision)
        idx = StateManager.load(project_dir)
        idx.decisions[did] = decision.decision[:40]
        idx.last_updated = __import__("datetime").datetime.now().isoformat()
        StateManager.save(project_dir, idx)
