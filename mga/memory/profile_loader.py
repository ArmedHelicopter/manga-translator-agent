"""Load character profiles from memory state and format for prompt injection."""

from __future__ import annotations

from pathlib import Path
from typing import Any
try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]

from mga.memory.entities import CharacterState
from mga.memory.state import StateManager


_PROFILE_METADATA_KEYS = (
    "last_reviewed_by",
    "last_reviewed_at",
    "last_reviewed_chapter",
    "confidence",
    "staleness_threshold",
)


def load_character_profile(project_dir: Path, character_id: str) -> CharacterState | None:
    """Load a single character profile from memory state."""
    profile = StateManager.get_character(project_dir, character_id)
    if profile is not None:
        return profile
    return _load_toml_profile(project_dir, character_id)


def load_all_profiles(project_dir: Path) -> dict[str, CharacterState]:
    """Load all character profiles, keyed by character_id."""
    profiles = _load_all_toml_profiles(project_dir)
    chars = StateManager.list_characters(project_dir)
    profiles.update({c.character_id: c for c in chars if c.character_id})
    return profiles


def _load_toml_profile(project_dir: Path, character_id: str) -> CharacterState | None:
    for profile in _iter_toml_profiles(project_dir):
        if profile.character_id == character_id:
            return profile
    return None


def _load_all_toml_profiles(project_dir: Path) -> dict[str, CharacterState]:
    return {
        profile.character_id: profile
        for profile in _iter_toml_profiles(project_dir)
        if profile.character_id
    }


def _iter_toml_profiles(project_dir: Path) -> list[CharacterState]:
    profiles_dir = project_dir / "character_profiles"
    if not profiles_dir.exists():
        return []
    profiles: list[CharacterState] = []
    for path in sorted(profiles_dir.rglob("*.toml")):
        profiles.append(_parse_toml_profile(path))
    return profiles


def _parse_toml_profile(path: Path) -> CharacterState:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    meta = data.get("meta", {}) if isinstance(data.get("meta", {}), dict) else {}
    character_id = str(meta.get("character_id") or data.get("character_id") or path.stem)
    provenance = meta.get("provenance", data.get("provenance", {}))
    if not isinstance(provenance, dict):
        provenance = {}
    else:
        provenance = dict(provenance)
    for key in _PROFILE_METADATA_KEYS:
        if key in meta:
            provenance[key] = meta[key]
    voice_evolutions = data.get("voice_evolution", data.get("voice_evolutions", []))
    if not isinstance(voice_evolutions, list):
        voice_evolutions = []
    return CharacterState(
        character_id=character_id,
        name_jp=str(meta.get("name_jp", data.get("name_jp", ""))),
        name_zh=str(meta.get("name_zh", data.get("name_zh", ""))),
        archetype=str(meta.get("archetype", data.get("archetype", ""))),
        speech_patterns=_stringify_mapping(data.get("speech_patterns", {})),
        catchphrases=_catchphrases(data.get("catchphrases", [])),
        tone_spectrum=_stringify_mapping(data.get("tone_spectrum", {})),
        translation_notes=_stringify_mapping(data.get("translation_notes", {})),
        relationship_speech=_relationship_speech(data.get("relationship_speech", {})),
        voice_evolutions=voice_evolutions,
        provenance=provenance,
    )


def _stringify_mapping(raw: object) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(value, list):
            result[str(key)] = ", ".join(str(item) for item in value)
        else:
            result[str(key)] = str(value)
    return result


def _catchphrases(raw: object) -> list[str]:
    if isinstance(raw, dict):
        raw = raw.get("patterns", [])
    if not isinstance(raw, list):
        return []
    return [str(item) for item in raw]


def _relationship_speech(raw: object) -> dict[str, dict[str, Any]]:
    if not isinstance(raw, dict):
        return {}
    rules: dict[str, dict[str, Any]] = {}
    for listener, value in raw.items():
        if not isinstance(value, dict):
            continue
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if isinstance(item, list):
                normalized[str(key)] = [str(part) for part in item]
            else:
                normalized[str(key)] = str(item)
        rules[str(listener)] = normalized
    return rules


def format_profile_for_prompt(profile: CharacterState) -> str:
    """Format a character profile into a structured prompt section.

    Returns a Chinese-language formatted block suitable for injection
    into a translation prompt.
    """
    parts = ["角色档案："]

    if profile.name_jp or profile.name_zh:
        name_line = f"- 名字：{profile.name_jp}"
        if profile.name_zh:
            name_line += f" → {profile.name_zh}"
        parts.append(name_line)

    if profile.archetype:
        parts.append(f"- 原型：{profile.archetype}")

    if profile.speech_patterns:
        patterns = "; ".join(f"{k}={v}" for k, v in profile.speech_patterns.items())
        parts.append(f"- 语言模式：{patterns}")

    if profile.catchphrases:
        parts.append(f"- 口头禅：{', '.join(profile.catchphrases)}")

    if profile.tone_spectrum:
        tones = "; ".join(f"{k}={v}" for k, v in profile.tone_spectrum.items())
        parts.append(f"- 语气：{tones}")

    if profile.translation_notes:
        notes = "; ".join(f"{k}={v}" for k, v in profile.translation_notes.items())
        parts.append(f"- 翻译注意：{notes}")

    if profile.relationship_speech:
        for listener, rule in profile.relationship_speech.items():
            details = "; ".join(
                f"{key}={', '.join(value) if isinstance(value, list) else value}"
                for key, value in rule.items()
            )
            parts.append(f"- relationship_speech[{listener}]: {details}")

    return "\n".join(parts)


def format_profiles_for_prompt(profiles: dict[str, CharacterState]) -> str:
    """Format multiple character profiles into prompt sections."""
    if not profiles:
        return ""
    sections = [format_profile_for_prompt(p) for p in profiles.values()]
    return "\n\n".join(sections)


def get_profile_as_dict(profile: CharacterState) -> dict[str, Any]:
    """Convert a CharacterState to a plain dict for context passing.

    Includes all fields relevant to translation and QA.
    """
    return {
        "character_id": profile.character_id,
        "name_jp": profile.name_jp,
        "name_zh": profile.name_zh,
        "archetype": profile.archetype,
        "speech_patterns": profile.speech_patterns,
        "catchphrases": profile.catchphrases,
        "tone_spectrum": profile.tone_spectrum,
        "translation_notes": profile.translation_notes,
        "relationship_speech": profile.relationship_speech,
    }
