"""Load character profiles from memory state and format for prompt injection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mga.memory.entities import CharacterState
from mga.memory.state import StateManager


def load_character_profile(project_dir: Path, character_id: str) -> CharacterState | None:
    """Load a single character profile from memory state."""
    return StateManager.get_character(project_dir, character_id)


def load_all_profiles(project_dir: Path) -> dict[str, CharacterState]:
    """Load all character profiles, keyed by character_id."""
    chars = StateManager.list_characters(project_dir)
    return {c.character_id: c for c in chars if c.character_id}


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
    }
