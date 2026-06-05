"""Build and enrich character profiles from translation observations."""

from __future__ import annotations

import re
from pathlib import Path
import tomli_w

from mga.memory.entities import CharacterState
from mga.memory.state import StateManager


# Regex for extracting sentence-ending particles (Japanese speech patterns)
_ENDING_PARTICLES = re.compile(r"[ぁ-ん]{1,3}[。！？…]$")
# Regex for catching repeated phrases
_PHRASE_RE = re.compile(r"[一-鿿぀-ゟ゠-ヿ]{2,8}")


def build_profile_from_translations(
    project_dir: Path,
    character_id: str,
    name_jp: str = "",
    name_zh: str = "",
) -> CharacterState:
    """Create a new character profile or load existing one.

    Args:
        project_dir: Project root directory.
        character_id: Unique character identifier.
        name_jp: Japanese name.
        name_zh: Chinese name.

    Returns:
        Existing profile or new empty CharacterState.
    """
    existing = StateManager.get_character(project_dir, character_id)
    if existing:
        return existing

    return CharacterState(
        character_id=character_id,
        name_jp=name_jp,
        name_zh=name_zh,
    )


def update_speech_patterns(
    profile: CharacterState,
    source_text: str,
    translated_text: str,
) -> CharacterState:
    """Update speech patterns based on a source->translation pair.

    Extracts sentence-ending particles and maps them to the
    translation equivalent.
    """
    # Extract Japanese ending particles
    match = _ENDING_PARTICLES.search(source_text)
    if match:
        jp_ending = match.group(0).rstrip("。！？…")
        if jp_ending and jp_ending not in profile.speech_patterns:
            # Try to infer Chinese equivalent from translated text
            zh_ending = ""
            if translated_text:
                last_char = translated_text[-1] if translated_text else ""
                if last_char in "。！？…~":
                    zh_ending = ""
                else:
                    # Extract last few chars as the equivalent
                    zh_match = re.search(r"[一-鿿]{1,3}$", translated_text.rstrip("。！？…~"))
                    if zh_match:
                        zh_ending = zh_match.group(0)

            profile.speech_patterns[jp_ending] = zh_ending or "保持原样"

    return profile


def update_catchphrases(
    profile: CharacterState,
    source_text: str,
    min_occurrences: int = 2,
) -> CharacterState:
    """Detect and add catchphrases from source text.

    A catchphrase is a 2-8 character CJK phrase that appears multiple times.
    This should be called with accumulated source texts for a character.
    """
    # This is a simplified version — in practice, you'd accumulate
    # across multiple calls and count occurrences
    phrases = _PHRASE_RE.findall(source_text)
    for phrase in phrases:
        if len(phrase) >= 3 and phrase not in profile.catchphrases:
            # Only add if it looks like a catchphrase (not a common word)
            profile.catchphrases.append(phrase)
            # Keep max 10 catchphrases
            if len(profile.catchphrases) > 10:
                profile.catchphrases = profile.catchphrases[-10:]

    return profile


def save_profile(project_dir: Path, profile: CharacterState) -> None:
    """Save a character profile to memory state."""
    StateManager.upsert_character(project_dir, profile)
    _write_profile_toml(project_dir, profile)


def _write_profile_toml(project_dir: Path, profile: CharacterState) -> Path | None:
    if not profile.character_id:
        return None
    out_dir = project_dir / "character_profiles"
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "character_id": profile.character_id,
        "name_jp": profile.name_jp,
        "name_zh": profile.name_zh,
        "archetype": profile.archetype,
    }
    if profile.provenance:
        meta["provenance"] = profile.provenance
    payload = {
        "meta": meta,
        "speech_patterns": profile.speech_patterns,
        "catchphrases": {"patterns": profile.catchphrases},
        "tone_spectrum": profile.tone_spectrum,
        "translation_notes": profile.translation_notes,
    }
    if profile.relationship_speech:
        payload["relationship_speech"] = profile.relationship_speech
    if profile.voice_evolutions:
        payload["voice_evolution"] = profile.voice_evolutions
    out_path = out_dir / f"{profile.character_id}.toml"
    out_path.write_text(tomli_w.dumps(payload), encoding="utf-8")
    return out_path


def build_and_save_profile(
    project_dir: Path,
    character_id: str,
    name_jp: str = "",
    name_zh: str = "",
    source_text: str = "",
    translated_text: str = "",
) -> CharacterState:
    """Build, enrich, and save a character profile in one call.

    Convenience function that combines load -> update -> save.
    """
    profile = build_profile_from_translations(project_dir, character_id, name_jp, name_zh)

    if source_text:
        profile = update_speech_patterns(profile, source_text, translated_text)
        profile = update_catchphrases(profile, source_text)

    save_profile(project_dir, profile)
    return profile
