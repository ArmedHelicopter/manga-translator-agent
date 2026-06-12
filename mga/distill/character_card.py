"""Character Card exporter for TavernAI/SillyTavern format.

TavernAI format specification:
- JSON with name, description, personality, scenario, first_dialogue, mes_example, data
- Extensions: talkativeness, description, personality, scenario, first_mes, mes_example, avatar
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from mga.memory.service import MemoryService, CharacterProfile
from mga.memory.entities import CharacterState


class CharacterCard(BaseModel):
    """TavernAI/SillyTavern character card format."""

    name: str = ""
    description: str = ""
    personality: str = ""
    scenario: str = ""
    first_mes: str = ""
    mes_example: str = ""
    avatar: str = ""
    talkativeness: float = 0.5

    # Extended fields (SillyTavern)
    creator: str = ""
    version: str = "1.0"
    tags: list[str] = Field(default_factory=list)
    created_at: str = ""

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.model_dump(exclude_none=True), ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, data: str | dict) -> "CharacterCard":
        if isinstance(data, str):
            data = json.loads(data)
        return cls(**data)


class CharacterCardExporter:
    """Export memory characters to TavernAI/SillyTavern format."""

    def __init__(self, project_dir: Path | str):
        self.project_dir = Path(project_dir)
        self._memory: MemoryService | None = None

    @property
    def memory(self) -> MemoryService:
        """Lazy-load memory service."""
        if self._memory is None:
            self._memory = MemoryService(self.project_dir)
            self._memory.initialize()
        return self._memory

    def export_character(self, character_id: str) -> CharacterCard:
        """Export a single character to card format."""
        profile = self.memory.get_character(character_id)
        if profile is None:
            raise ValueError(f"Character not found: {character_id}")
        return self._profile_to_card(profile)

    def export_all(self) -> list[CharacterCard]:
        """Export all characters to card format."""
        return [self._profile_to_card(p) for p in self.memory.list_characters()]

    def _profile_to_card(self, profile: CharacterProfile | CharacterState) -> CharacterCard:
        """Convert memory profile to TavernAI card."""
        name = profile.name_zh or profile.name_jp or profile.character_id

        # Build personality description
        personality_parts = []
        if profile.archetype:
            personality_parts.append(f"原型: {profile.archetype}")
        if profile.speech_patterns:
            patterns = "; ".join(f"{k}={v}" for k, v in profile.speech_patterns.items())
            personality_parts.append(f"说话模式: {patterns}")
        if profile.tone_spectrum:
            tones = "; ".join(f"{k}={v}" for k, v in profile.tone_spectrum.items())
            personality_parts.append(f"语气: {tones}")

        personality = "\n".join(personality_parts) if personality_parts else "Unknown personality"

        # Build full description
        desc_parts = [f"角色ID: {profile.character_id}"]
        if profile.name_jp:
            desc_parts.append(f"日文名: {profile.name_jp}")
        if profile.name_zh:
            desc_parts.append(f"中文名: {profile.name_zh}")
        if profile.archetype:
            desc_parts.append(f"角色原型: {profile.archetype}")
        if profile.catchphrases:
            desc_parts.append(f"口头禅: {', '.join(profile.catchphrases)}")
        if profile.translation_notes:
            notes = "; ".join(f"{k}={v}" for k, v in profile.translation_notes.items())
            desc_parts.append(f"翻译注意: {notes}")

        description = "\n".join(desc_parts)

        # Build relationship context as scenario
        scenario_parts = ["## Relationships"]
        for listener, rel_data in profile.relationships.items():
            rel_str = f"- 对{listener}: "
            rel_parts = []
            if rel_data.get("honorific"):
                rel_parts.append(f"敬语: {rel_data['honorific']}")
            if rel_data.get("formality"):
                rel_parts.append(f"亲疏: {rel_data['formality']}")
            if rel_data.get("relationship"):
                rel_parts.append(f"关系: {rel_data['relationship']}")
            if rel_parts:
                rel_str += ", ".join(rel_parts)
                scenario_parts.append(rel_str)
        scenario = "\n".join(scenario_parts)

        # Build example dialogue
        example_parts = []
        for i, phrase in enumerate(profile.catchphrases[:3], 1):
            example_parts.append(f"Example {i}: \"{phrase}\"")
        mes_example = "\n".join(example_parts) if example_parts else "Example 1: \"...\""

        # Detect talkativeness from voice evolutions
        talkativeness = self._estimate_talkativeness(profile)

        return CharacterCard(
            name=name,
            description=description,
            personality=personality,
            scenario=scenario,
            first_mes=f"{name}开始说话。",
            mes_example=mes_example,
            talkativeness=talkativeness,
            tags=self._build_tags(profile),
        )

    def _estimate_talkativeness(self, profile: CharacterProfile | CharacterState) -> float:
        """Estimate talkativeness score from voice evolutions."""
        if hasattr(profile, "voice_evolutions") and profile.voice_evolutions:
            # Active voice changers tend to talk more
            return 0.7
        if hasattr(profile, "catchphrases") and len(profile.catchphrases) > 0:
            return 0.6
        return 0.5

    def _build_tags(self, profile: CharacterProfile | CharacterState) -> list[str]:
        """Build tags from profile metadata."""
        tags = []
        if profile.archetype:
            tags.append(f"archetype:{profile.archetype}")
        if profile.name_jp:
            tags.append(f"jp-name:{profile.name_jp}")
        return tags

    def save(
        self,
        output_dir: Path | str,
        format: str = "json",
    ) -> list[Path]:
        """Export all characters to output directory.

        Args:
            output_dir: Directory to save character cards
            format: Output format (json or toml, default json)

        Returns:
            List of saved file paths
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        cards = self.export_all()
        saved_paths = []

        for card in cards:
            safe_name = self._sanitize_filename(card.name)
            path = output_dir / f"{safe_name}.json"
            path.write_text(card.to_json(), encoding="utf-8")
            saved_paths.append(path)

        return saved_paths

    def _sanitize_filename(self, name: str) -> str:
        """Sanitize name for use as filename."""
        import re
        safe = re.sub(r'[<>:"/\\|?*]', "_", name)
        safe = safe.strip(". ")
        return safe or "character"