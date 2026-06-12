"""Importers for community formats back into memory system.

Supports:
- Character Card: TavernAI/SillyTavern → memory profile
- Lorebook: NovelAI/AI Dungeon → memory terms/scenes
- Hermes Agent Skill: Hermes-compatible agent skill → memory profile
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from mga.memory.service import MemoryService, CharacterProfile, TermEntry, SceneContext
from mga.memory.state import StateManager
from mga.memory.entities import CharacterState, TermState, SceneState

from .character_card import CharacterCard
from .lorebook import Lorebook, LorebookEntry


class HermesSkill(BaseModel):
    """Hermes agent skill format — declarative YAML/JSON skill definition.

    Based on the Hermes agent framework skill specification:
    - YAML or JSON serializable
    - Fields: name, description, version, instruction, variables, triggers, constraints, examples
    - Used to define agent capabilities for character roleplay

    Format version: 1.0
    """

    name: str = ""
    description: str = ""
    version: str = "1.0"
    instruction: str = ""
    variables: dict[str, Any] = Field(default_factory=dict)
    triggers: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    examples: list[dict[str, str]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(
            self.model_dump(exclude_none=True, exclude_defaults=True),
            ensure_ascii=False, indent=indent,
        )

    def to_yaml(self) -> str:
        """Serialize to YAML string."""
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML not installed. Install with: pip install pyyaml")
        return yaml.dump(
            self.model_dump(exclude_none=True, exclude_defaults=True),
            allow_unicode=True, default_flow_style=False, sort_keys=False,
        )

    @classmethod
    def from_json(cls, data: str | dict) -> "HermesSkill":
        if isinstance(data, str):
            data = json.loads(data)
        return cls(**data)

    @classmethod
    def from_yaml(cls, data: str) -> "HermesSkill":
        """Deserialize from YAML string."""
        try:
            import yaml
        except ImportError:
            raise ImportError("PyYAML not installed. Install with: pip install pyyaml")
        parsed = yaml.safe_load(data)
        if not isinstance(parsed, dict):
            raise ValueError("YAML content must be a mapping")
        return cls(**parsed)


class CharacterCardImporter:
    """Import TavernAI/SillyTavern character cards into memory system."""

    def __init__(self, project_dir: Path | str):
        self.project_dir = Path(project_dir)
        self._memory = None

    @property
    def memory(self) -> MemoryService:
        """Lazy-load memory service."""
        if self._memory is None:
            self._memory = MemoryService(self.project_dir)
            self._memory.initialize()
        return self._memory

    def import_card(self, card: CharacterCard | str | Path) -> CharacterProfile:
        """Import a character card into memory.

        Args:
            card: CharacterCard instance, JSON string, or file path

        Returns:
            Created or updated CharacterProfile
        """
        if isinstance(card, (str, Path)):
            card = self._load_card(card)

        # Extract profile from card
        profile = self._card_to_profile(card)

        # Save to memory
        character_id = self._sanitize_id(card.name)
        self.memory.update_character(
            character_id,
            name_jp=self._extract_jp_name(card.description),
            name_zh=card.name,
            archetype=self._extract_archetype(card.personality),
            speech_patterns=self._extract_speech_patterns(card.personality),
            catchphrases=self._extract_catchphrases(card.mes_example),
        )

        return self.memory.get_character(character_id)

    def import_file(self, card_path: Path | str) -> CharacterProfile:
        """Import a character card from file."""
        card_path = Path(card_path)
        data = json.loads(card_path.read_text(encoding="utf-8"))
        card = CharacterCard(**data)
        return self.import_card(card)

    def import_directory(self, dir_path: Path | str) -> list[CharacterProfile]:
        """Import all character cards from a directory."""
        dir_path = Path(dir_path)
        profiles = []
        for card_path in dir_path.glob("*.json"):
            try:
                profile = self.import_file(card_path)
                profiles.append(profile)
            except Exception as e:
                # Skip invalid cards
                continue
        return profiles

    def _load_card(self, card: str | Path) -> CharacterCard:
        """Load card from string or path."""
        if isinstance(card, Path):
            data = json.loads(card.read_text(encoding="utf-8"))
        else:
            data = json.loads(card)
        return CharacterCard(**data)

    def _card_to_profile(self, card: CharacterCard) -> dict:
        """Convert card fields to profile dict."""
        return {
            "name_zh": card.name,
            "name_jp": self._extract_jp_name(card.description),
            "archetype": self._extract_archetype(card.personality),
            "speech_patterns": self._extract_speech_patterns(card.personality),
            "catchphrases": self._extract_catchphrases(card.mes_example),
        }

    def _sanitize_id(self, name: str) -> str:
        """Create valid character ID from name."""
        import re
        safe = re.sub(r'[^a-zA-Z0-9_-]', '_', name.lower())
        return safe or "character"

    def _extract_jp_name(self, text: str) -> str:
        """Extract Japanese name from description."""
        import re
        match = re.search(r'日文名[:：]\s*(.+)', text)
        return match.group(1).strip() if match else ""

    def _extract_archetype(self, text: str) -> str:
        """Extract archetype from personality."""
        import re
        # Try both patterns: "原型" or "角色原型"
        match = re.search(r'角色原型[:：]\s*(.+)', text)
        if not match:
            match = re.search(r'原型[:：]\s*(.+)', text)
        return match.group(1).strip() if match else ""

    def _extract_speech_patterns(self, text: str) -> dict[str, str]:
        """Extract speech patterns from personality."""
        patterns = {}
        import re
        for match in re.finditer(r'说话模式[:：]\s*(.+)', text):
            pattern_text = match.group(1).strip()
            for part in pattern_text.split(';'):
                if '=' in part:
                    k, v = part.split('=', 1)
                    patterns[k.strip()] = v.strip()
        return patterns

    def _extract_catchphrases(self, text: str) -> list[str]:
        """Extract catchphrases from example dialogue."""
        import re
        phrases = []
        for match in re.finditer(r'"([^"]+)"', text):
            phrases.append(match.group(1))
        return phrases[:5]  # Limit to 5 catchphrases


class LorebookImporter:
    """Import NovelAI/AI Dungeon lorebook into memory system."""

    def __init__(self, project_dir: Path | str):
        self.project_dir = Path(project_dir)
        self._memory = None

    @property
    def memory(self) -> MemoryService:
        """Lazy-load memory service."""
        if self._memory is None:
            self._memory = MemoryService(self.project_dir)
            self._memory.initialize()
        return self._memory

    def import_lorebook(self, lorebook: Lorebook | str | Path) -> dict[str, int]:
        """Import a lorebook into memory.

        Args:
            lorebook: Lorebook instance, JSON string, or file path

        Returns:
            Statistics: {"characters": n, "terms": n, "scenes": n}
        """
        if isinstance(lorebook, (str, Path)):
            lorebook = self._load_lorebook(lorebook)

        stats = {"characters": 0, "terms": 0, "scenes": 0}

        for entry in lorebook.entries:
            lore_key = entry.loreKey or ""
            if lore_key.startswith("character:"):
                self._import_character_entry(entry)
                stats["characters"] += 1
            elif lore_key.startswith("term:"):
                self._import_term_entry(entry)
                stats["terms"] += 1
            elif lore_key.startswith("scene:"):
                self._import_scene_entry(entry)
                stats["scenes"] += 1
            else:
                # Default: import as term
                self._import_term_entry(entry)
                stats["terms"] += 1

        return stats

    def import_file(self, lorebook_path: Path | str) -> dict[str, int]:
        """Import a lorebook from file."""
        lorebook_path = Path(lorebook_path)
        data = json.loads(lorebook_path.read_text(encoding="utf-8"))
        lorebook = Lorebook(**data)
        return self.import_lorebook(lorebook)

    def _load_lorebook(self, lorebook: str | Path) -> Lorebook:
        """Load lorebook from string or path."""
        if isinstance(lorebook, Path):
            data = json.loads(lorebook.read_text(encoding="utf-8"))
        else:
            data = json.loads(lorebook)
        return Lorebook(**data)

    def _import_character_entry(self, entry: LorebookEntry) -> None:
        """Import a character lorebook entry."""
        character_id = entry.loreKey.replace("character:", "")
        name = self._extract_title(entry.entry)

        self.memory.get_or_create_character(character_id)
        self.memory.update_character(
            character_id,
            name_zh=name,
            name_jp=self._extract_field(entry.entry, "日文名"),
            archetype=self._extract_field(entry.entry, "角色类型"),
            speech_patterns=self._extract_patterns(entry.entry),
            catchphrases=self._extract_catchphrases_from_entry(entry.entry),
        )

    def _import_term_entry(self, entry: LorebookEntry) -> None:
        """Import a term lorebook entry."""
        term_id = entry.loreKey.replace("term:", "") if ":" in entry.loreKey else entry.key[0] if entry.key else "unknown"

        term_jp = self._extract_title(entry.entry)
        term_zh = self._extract_field(entry.entry, "翻译")

        if term_jp and term_zh:
            self.memory.register_term(
                term_jp=term_jp,
                term_zh=term_zh,
                context=self._extract_field(entry.entry, "语境"),
                strategy=self._extract_field(entry.entry, "策略"),
            )

    def _import_scene_entry(self, entry: LorebookEntry) -> None:
        """Import a scene lorebook entry."""
        scene_id = entry.loreKey.replace("scene:", "") if ":" in entry.loreKey else entry.key[0] if entry.key else "unknown"

        chapter = self._extract_int(entry.entry, "章节")
        page = self._extract_int(entry.entry, "页码")

        scene = self.memory.get_or_create_scene(scene_id)
        self.memory.update_scene(
            scene_id,
            chapter=chapter,
            page=page,
            description=self._extract_field(entry.entry, "场景描述"),
            mood=self._extract_field(entry.entry, "氛围"),
            summary=self._extract_field(entry.entry, "叙述"),
        )

    def _extract_title(self, text: str) -> str:
        """Extract title from markdown entry."""
        import re
        match = re.search(r'^#\s*(.+)$', text, re.MULTILINE)
        return match.group(1).strip() if match else text.split('\n')[0][:50]

    def _extract_field(self, text: str, field_name: str) -> str:
        """Extract field value from entry text."""
        import re
        match = re.search(rf'{field_name}[:：]\s*(.+)', text)
        return match.group(1).strip() if match else ""

    def _extract_int(self, text: str, field_name: str) -> int:
        """Extract integer field value."""
        value = self._extract_field(text, field_name)
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0

    def _extract_patterns(self, text: str) -> dict[str, str]:
        """Extract speech patterns from text."""
        patterns = {}
        import re
        match = re.search(r'说话模式[:：]\s*(.+)', text)
        if match:
            pattern_text = match.group(1).strip()
            for part in pattern_text.split(';'):
                if '=' in part:
                    k, v = part.split('=', 1)
                    patterns[k.strip()] = v.strip()
        return patterns

    def _extract_catchphrases_from_entry(self, text: str) -> list[str]:
        """Extract catchphrases from entry text."""
        import re
        phrases = []
        match = re.search(r'口头禅[:：]\s*(.+)', text)
        if match:
            catch_text = match.group(1).strip()
            for phrase in catch_text.split(','):
                phrase = phrase.strip()
                if phrase:
                    phrases.append(phrase)
        return phrases[:5]


class HermesSkillImporter:
    """Import/Export Hermes agent skill format.

    The Hermes agent skill format is a YAML/JSON-based declarative specification
    for defining agent capabilities. It is used to let Hermes-compatible agents
    adopt a specific character's persona, speech patterns, and behavioral constraints.

    Format fields:
    - name: Skill identifier (e.g. "act_as_sakura")
    - description: Human-readable summary
    - version: Format version (default "1.0")
    - instruction: System prompt / behavioral instructions
    - variables: Parameterizable values (character_name, archetype, etc.)
    - triggers: Keywords/patterns that activate this skill
    - constraints: Behavioral guardrails
    - examples: Few-shot input/output pairs
    - metadata: Extra key-value data
    """

    def __init__(self, project_dir: Path | str):
        self.project_dir = Path(project_dir)
        self._memory = None

    @property
    def memory(self) -> MemoryService:
        """Lazy-load memory service."""
        if self._memory is None:
            self._memory = MemoryService(self.project_dir)
            self._memory.initialize()
        return self._memory

    def export_skill(self, character_id: str) -> HermesSkill:
        """Export character as a Hermes agent skill definition.

        Args:
            character_id: The character to export

        Returns:
            HermesSkill with full character persona encoded

        Raises:
            ValueError: If character not found
        """
        profile = self.memory.get_character(character_id)
        if profile is None:
            raise ValueError(f"Character not found: {character_id}")

        name = profile.name_zh or profile.name_jp or character_id
        sanitized = self._sanitize_id(name)
        # Use character_id if sanitized is empty or just underscores
        skill_name = f"act_as_{sanitized if sanitized.strip('_') else character_id}"

        # Build instruction from profile
        instruction = self._build_instruction(profile)

        # Build variables — parametric values that can be overridden
        variables = self._build_variables(profile)

        # Build triggers — keywords that activate the skill
        triggers = self._build_triggers(profile)

        # Build constraints — behavioral guardrails
        constraints = self._build_constraints(profile)

        # Build examples from catchphrases
        examples = self._build_examples(profile)

        # Metadata
        skill_metadata: dict[str, Any] = {
            "character_id": character_id,
            "source": "mga-distill",
        }
        if profile.name_jp:
            skill_metadata["name_jp"] = profile.name_jp
        if profile.name_zh:
            skill_metadata["name_zh"] = profile.name_zh

        return HermesSkill(
            name=skill_name,
            description=f"Act as {name} — {profile.archetype or 'character'} persona for manga translation",
            version="1.0",
            instruction=instruction,
            variables=variables,
            triggers=triggers,
            constraints=constraints,
            examples=examples,
            metadata=skill_metadata,
        )

    def export_skill_file(self, character_id: str, output_path: Path | str, fmt: str = "yaml") -> Path:
        """Export character as a Hermes skill file.

        Args:
            character_id: The character to export
            output_path: File path to write (should end in .yaml or .json)
            fmt: Output format ("yaml" or "json")

        Returns:
            Path to the written file
        """
        skill = self.export_skill(character_id)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "yaml":
            output_path.write_text(skill.to_yaml(), encoding="utf-8")
        else:
            output_path.write_text(skill.to_json(), encoding="utf-8")

        return output_path

    def import_skill(self, skill_data: dict | HermesSkill | str | Path) -> str:
        """Import a Hermes skill definition into memory.

        Args:
            skill_data: HermesSkill instance, dict, JSON string, YAML string, or file path

        Returns:
            Created character_id
        """
        skill = self._load_skill(skill_data)

        # Derive character ID from skill name
        char_id = skill.name.replace("act_as_", "") if skill.name else "unknown"
        character_id = self.memory.get_or_create_character(char_id).character_id

        # Extract name from variables or instruction
        character_name = skill.variables.get("character_name", "")
        archetype = skill.variables.get("archetype", "")

        # Extract speech patterns from instruction
        speech_patterns = self._extract_speech_patterns(skill.instruction)

        # Extract catchphrases from examples
        catchphrases = self._extract_catchphrases_from_examples(skill.examples)

        # Extract tone from constraints
        tone_spectrum = self._extract_tone_from_constraints(skill.constraints)

        # Derive names from metadata or variables
        name_jp = skill.metadata.get("name_jp", "")
        name_zh = skill.metadata.get("name_zh", character_name)

        self.memory.update_character(
            character_id,
            name_jp=name_jp,
            name_zh=name_zh or character_name,
            archetype=archetype,
            speech_patterns=speech_patterns,
            catchphrases=catchphrases,
            tone_spectrum=tone_spectrum,
        )

        return character_id

    def import_file(self, skill_path: Path | str) -> str:
        """Import a Hermes skill from a file (YAML or JSON).

        Args:
            skill_path: Path to the skill file

        Returns:
            Created character_id
        """
        skill_path = Path(skill_path)
        content = skill_path.read_text(encoding="utf-8")

        if skill_path.suffix in (".yaml", ".yml"):
            skill = HermesSkill.from_yaml(content)
        else:
            skill = HermesSkill.from_json(content)

        return self.import_skill(skill)

    # -- Private helpers ---------------------------------------------------

    def _load_skill(self, skill_data: dict | HermesSkill | str | Path) -> HermesSkill:
        """Load a HermesSkill from various input types."""
        if isinstance(skill_data, HermesSkill):
            return skill_data
        if isinstance(skill_data, dict):
            return HermesSkill(**skill_data)
        if isinstance(skill_data, Path):
            content = skill_data.read_text(encoding="utf-8")
            if skill_data.suffix in (".yaml", ".yml"):
                return HermesSkill.from_yaml(content)
            return HermesSkill.from_json(content)
        if isinstance(skill_data, str):
            # Try JSON first, then YAML
            try:
                return HermesSkill.from_json(skill_data)
            except (json.JSONDecodeError, ValueError):
                return HermesSkill.from_yaml(skill_data)
        raise ValueError(f"Unsupported skill data type: {type(skill_data)}")

    def _build_instruction(self, profile: CharacterProfile | CharacterState) -> str:
        """Build skill instruction from profile."""
        name = profile.name_zh or profile.name_jp or profile.character_id
        parts = [f"You are {name}."]

        if profile.archetype:
            parts.append(f"Character type: {profile.archetype}.")

        if profile.speech_patterns:
            patterns = ", ".join(f"{k}: {v}" for k, v in profile.speech_patterns.items())
            parts.append(f"Speech patterns: {patterns}.")

        if profile.catchphrases:
            phrases = ", ".join(f'"{p}"' for p in profile.catchphrases[:5])
            parts.append(f"Common expressions: {phrases}.")

        if profile.tone_spectrum:
            tones = ", ".join(f"{k}: {v}" for k, v in profile.tone_spectrum.items())
            parts.append(f"Tone: {tones}.")

        if profile.relationships:
            rel_parts = []
            for listener, rel_data in profile.relationships.items():
                rel = rel_data.get("relationship", "")
                if rel:
                    rel_parts.append(f"to {listener}: {rel}")
            if rel_parts:
                parts.append(f"Relationships: {'; '.join(rel_parts)}.")

        return " ".join(parts)

    def _build_variables(self, profile: CharacterProfile | CharacterState) -> dict[str, Any]:
        """Build skill variables from profile."""
        variables: dict[str, Any] = {
            "character_name": profile.name_zh or profile.name_jp or profile.character_id,
        }
        if profile.archetype:
            variables["archetype"] = profile.archetype
        if profile.name_jp:
            variables["name_jp"] = profile.name_jp
        if profile.name_zh:
            variables["name_zh"] = profile.name_zh
        return variables

    def _build_triggers(self, profile: CharacterProfile | CharacterState) -> list[str]:
        """Build trigger keywords from profile."""
        triggers = []
        if profile.name_jp:
            triggers.append(profile.name_jp)
        if profile.name_zh:
            triggers.append(profile.name_zh)
        char_id = profile.character_id
        if char_id and char_id not in triggers:
            triggers.append(char_id)
        if profile.catchphrases:
            # First catchphrase as trigger
            triggers.append(profile.catchphrases[0])
        return triggers

    def _build_constraints(self, profile: CharacterProfile | CharacterState) -> list[str]:
        """Build behavioral constraints from profile."""
        constraints = ["Stay in character at all times."]
        if profile.speech_patterns:
            constraints.append("Follow the specified speech patterns consistently.")
        if profile.relationships:
            constraints.append("Respect established relationships and formality levels.")
        if profile.tone_spectrum:
            constraints.append("Maintain consistent emotional tone.")
        return constraints

    def _build_examples(self, profile: CharacterProfile | CharacterState) -> list[dict[str, str]]:
        """Build few-shot examples from catchphrases."""
        examples = []
        for phrase in profile.catchphrases[:3]:
            examples.append({
                "input": f"What would {profile.name_zh or profile.name_jp or profile.character_id} say?",
                "output": phrase,
            })
        return examples

    def _extract_speech_patterns(self, instruction: str) -> dict[str, str]:
        """Extract speech patterns from skill instruction."""
        import re
        patterns = {}
        match = re.search(r'Speech patterns:\s*(.+?)\.', instruction)
        if match:
            pattern_text = match.group(1).strip()
            for part in pattern_text.split(','):
                if ':' in part:
                    k, v = part.split(':', 1)
                    patterns[k.strip()] = v.strip()
        return patterns

    def _extract_catchphrases_from_examples(self, examples: list[dict[str, str]]) -> list[str]:
        """Extract catchphrases from skill examples."""
        return [ex["output"] for ex in examples if "output" in ex][:5]

    def _extract_tone_from_constraints(self, constraints: list[str]) -> dict[str, str]:
        """Extract tone information from constraints."""
        tones = {}
        for c in constraints:
            if "tone" in c.lower():
                tones["tone_constraint"] = c
        return tones

    def _sanitize_id(self, name: str) -> str:
        """Create valid identifier from name."""
        import re
        safe = re.sub(r'[^a-zA-Z0-9_-]', '_', name.lower())
        return safe or "character"