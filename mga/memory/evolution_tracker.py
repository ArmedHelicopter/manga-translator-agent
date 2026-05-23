"""Track character voice evolution — formality changes, tone shifts, etc."""

from __future__ import annotations

import logging
import tomli_w
from datetime import datetime
from pathlib import Path
from typing import Any

from .entities import CharacterState
from .state import StateManager

logger = logging.getLogger(__name__)


class EvolutionTracker:
    """Track and record character voice changes over time."""

    def __init__(self, project_dir: Path) -> None:
        self.project_dir = project_dir
        self._changelog_path = project_dir / "memory" / "learned" / "voice_changelog.toml"

    def detect_changes(
        self,
        character_id: str,
        new_speech_patterns: dict[str, str],
        new_tone: dict[str, str] | None = None,
        chapter: int = 0,
        page: int = 0,
    ) -> list[dict[str, Any]]:
        """Compare new observations with existing profile and detect changes.

        Returns a list of change records.
        """
        profile = StateManager.get_character(self.project_dir, character_id)
        if not profile:
            return []

        changes: list[dict[str, Any]] = []

        # Check speech pattern changes
        for jp_ending, zh_equiv in new_speech_patterns.items():
            existing = profile.speech_patterns.get(jp_ending)
            if existing is None:
                changes.append({
                    "type": "speech_pattern_new",
                    "character_id": character_id,
                    "field": f"speech_patterns.{jp_ending}",
                    "old_value": None,
                    "new_value": zh_equiv,
                    "chapter": chapter,
                    "page": page,
                    "timestamp": datetime.now().isoformat(),
                })
            elif existing != zh_equiv:
                changes.append({
                    "type": "speech_pattern_changed",
                    "character_id": character_id,
                    "field": f"speech_patterns.{jp_ending}",
                    "old_value": existing,
                    "new_value": zh_equiv,
                    "chapter": chapter,
                    "page": page,
                    "timestamp": datetime.now().isoformat(),
                })

        # Check tone changes
        if new_tone:
            for context, tone in new_tone.items():
                existing = profile.tone_spectrum.get(context)
                if existing is None:
                    changes.append({
                        "type": "tone_new",
                        "character_id": character_id,
                        "field": f"tone_spectrum.{context}",
                        "old_value": None,
                        "new_value": tone,
                        "chapter": chapter,
                        "page": page,
                        "timestamp": datetime.now().isoformat(),
                    })
                elif existing != tone:
                    changes.append({
                        "type": "tone_changed",
                        "character_id": character_id,
                        "field": f"tone_spectrum.{context}",
                        "old_value": existing,
                        "new_value": tone,
                        "chapter": chapter,
                        "page": page,
                        "timestamp": datetime.now().isoformat(),
                    })

        return changes

    def record_changes(self, changes: list[dict[str, Any]]) -> None:
        """Write changes to the voice changelog TOML file."""
        if not changes:
            return

        self._changelog_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing changelog
        existing: list[dict[str, Any]] = []
        if self._changelog_path.exists():
            try:
                import tomli
                with open(self._changelog_path, "rb") as f:
                    data = tomli.load(f)
                existing = data.get("changes", [])
            except Exception:
                existing = []

        existing.extend(changes)

        # Write back
        data = {"changes": existing}
        self._changelog_path.write_text(
            tomli_w.dumps(data),
            encoding="utf-8",
        )
        logger.info("Recorded %d voice changes to %s", len(changes), self._changelog_path)

    def update_profile(
        self,
        character_id: str,
        changes: list[dict[str, Any]],
    ) -> CharacterState | None:
        """Apply detected changes to the character profile."""
        profile = StateManager.get_character(self.project_dir, character_id)
        if not profile:
            return None

        for change in changes:
            field = change.get("field", "")
            new_value = change.get("new_value")

            if field.startswith("speech_patterns."):
                key = field.split(".", 1)[1]
                if new_value is not None:
                    profile.speech_patterns[key] = new_value
            elif field.startswith("tone_spectrum."):
                key = field.split(".", 1)[1]
                if new_value is not None:
                    profile.tone_spectrum[key] = new_value

        # Add to voice_evolutions
        profile.voice_evolutions.append({
            "chapter": changes[0].get("chapter", 0) if changes else 0,
            "page": changes[0].get("page", 0) if changes else 0,
            "changes": [
                {"field": c["field"], "old": c.get("old_value"), "new": c.get("new_value")}
                for c in changes
            ],
            "timestamp": datetime.now().isoformat(),
        })

        StateManager.upsert_character(self.project_dir, profile)
        return profile

    def get_changelog(self) -> list[dict[str, Any]]:
        """Read the full changelog."""
        if not self._changelog_path.exists():
            return []

        try:
            import tomli
            with open(self._changelog_path, "rb") as f:
                data = tomli.load(f)
            return data.get("changes", [])
        except Exception:
            return []

    def get_changes_for_character(self, character_id: str) -> list[dict[str, Any]]:
        """Filter changelog to a specific character."""
        return [
            c for c in self.get_changelog()
            if c.get("character_id") == character_id
        ]
