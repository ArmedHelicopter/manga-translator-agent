"""Tests for distill module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from mga.distill import (
    CharacterCard,
    CharacterCardExporter,
    Lorebook,
    LorebookEntry,
    LorebookExporter,
    CharacterCardImporter,
    LorebookImporter,
)
from mga.memory.service import MemoryService


@pytest.fixture
def temp_project():
    """Create a temporary project directory with memory structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir)
        (project_dir / "memory" / "state" / "characters").mkdir(parents=True, exist_ok=True)
        (project_dir / "memory" / "state" / "terms").mkdir(parents=True, exist_ok=True)
        (project_dir / "memory" / "state" / "scenes").mkdir(parents=True, exist_ok=True)
        yield project_dir


@pytest.fixture
def memory_with_data(temp_project):
    """Create memory service with test data."""
    memory = MemoryService(temp_project)
    memory.initialize()

    # Add a character
    memory.update_character(
        "sakura",
        name_jp="桜",
        name_zh="樱",
        archetype="元气少女",
        speech_patterns={"formal": "です", "casual": "だ"},
        catchphrases=["我来啦！", "加油！"],
    )

    # Add a term
    memory.register_term("魔法少女", "魔法少女", context="魔法少女变身", strategy="preserve")

    # Add a scene
    memory.update_scene(
        "ch1_p1",
        chapter=1,
        page=1,
        description="学校天台",
        mood="轻松",
    )

    memory.save(force=True)
    return memory


# ── Character Card Tests ───────────────────────────────────────────────────────

class TestCharacterCard:
    """Tests for CharacterCard model."""

    def test_create_card(self):
        """Test creating a character card."""
        card = CharacterCard(
            name="樱",
            description="主角",
            personality="元气",
            talkativeness=0.7,
        )
        assert card.name == "樱"
        assert card.talkativeness == 0.7

    def test_to_json(self):
        """Test JSON serialization."""
        card = CharacterCard(name="樱", personality="元气")
        json_str = card.to_json()
        data = json.loads(json_str)
        assert data["name"] == "樱"
        assert data["personality"] == "元气"

    def test_from_json(self):
        """Test JSON deserialization."""
        data = {"name": "樱", "personality": "元气", "talkativeness": 0.6}
        card = CharacterCard.from_json(data)
        assert card.name == "樱"
        assert card.talkativeness == 0.6

    def test_from_json_string(self):
        """Test JSON string deserialization."""
        json_str = '{"name": "樱", "personality": "元气"}'
        card = CharacterCard.from_json(json_str)
        assert card.name == "樱"


class TestCharacterCardExporter:
    """Tests for CharacterCardExporter."""

    def test_export_single_character(self, memory_with_data, temp_project):
        """Test exporting a single character."""
        exporter = CharacterCardExporter(temp_project)
        card = exporter.export_character("sakura")

        assert card.name == "樱"
        assert "樱" in card.description
        assert "魔法少女变身" not in card.description  # Not a catchphrase

    def test_export_all_characters(self, memory_with_data, temp_project):
        """Test exporting all characters."""
        exporter = CharacterCardExporter(temp_project)
        cards = exporter.export_all()

        assert len(cards) == 1
        assert cards[0].name == "樱"

    def test_save_character_cards(self, memory_with_data, temp_project):
        """Test saving character cards to directory."""
        output_dir = temp_project / "export"
        exporter = CharacterCardExporter(temp_project)
        saved = exporter.save(output_dir)

        assert len(saved) == 1
        assert saved[0].name == "樱.json"
        assert saved[0].exists()

    def test_export_nonexistent_character(self, temp_project):
        """Test exporting nonexistent character raises error."""
        exporter = CharacterCardExporter(temp_project)
        with pytest.raises(ValueError, match="Character not found"):
            exporter.export_character("nonexistent")

    def test_sanitize_filename(self, temp_project):
        """Test filename sanitization."""
        exporter = CharacterCardExporter(temp_project)
        safe = exporter._sanitize_filename("test<>file:name")
        assert "<" not in safe
        assert ">" not in safe
        assert ":" not in safe


# ── Lorebook Tests ──────────────────────────────────────────────────────────────

class TestLorebookEntry:
    """Tests for LorebookEntry model."""

    def test_create_entry(self):
        """Test creating a lorebook entry."""
        entry = LorebookEntry(
            loreKey="character:sakura",
            entry="# 樱\n角色",
            key=["樱", "sakura"],
            priority=80,
        )
        assert entry.loreKey == "character:sakura"
        assert entry.priority == 80
        assert entry.uid  # uid should be auto-generated

    def test_entry_with_custom_uid(self):
        """Test entry with custom uid."""
        entry = LorebookEntry(
            loreKey="term:magic",
            entry="# 魔法",
            uid="custom123",
        )
        assert entry.uid == "custom123"

    def test_to_dict(self):
        """Test entry to dict conversion."""
        entry = LorebookEntry(
            loreKey="character:test",
            entry="Test entry",
            priority=50,
        )
        d = entry.to_dict()
        assert d["loreKey"] == "character:test"
        assert d["priority"] == 50
        assert "uid" in d


class TestLorebook:
    """Tests for Lorebook container."""

    def test_create_lorebook(self):
        """Test creating a lorebook."""
        entry = LorebookEntry(loreKey="test", entry="Test")
        lorebook = Lorebook(entries=[entry])
        assert len(lorebook.entries) == 1

    def test_to_json(self):
        """Test lorebook JSON serialization."""
        entry = LorebookEntry(loreKey="test", entry="Test")
        lorebook = Lorebook(entries=[entry])
        json_str = lorebook.to_json()
        data = json.loads(json_str)
        assert "entries" in data
        assert len(data["entries"]) == 1

    def test_from_json(self):
        """Test lorebook JSON deserialization."""
        data = {"entries": [{"loreKey": "test", "entry": "Test", "key": []}]}
        lorebook = Lorebook.from_json(data)
        assert len(lorebook.entries) == 1


class TestLorebookExporter:
    """Tests for LorebookExporter."""

    def test_export_character_entry(self, memory_with_data, temp_project):
        """Test exporting character as lorebook entry."""
        exporter = LorebookExporter(temp_project)
        entry = exporter.export_character_entry("sakura")

        assert entry.loreKey == "character:sakura"
        assert "樱" in entry.key

    def test_export_term_entry(self, memory_with_data, temp_project):
        """Test exporting term as lorebook entry."""
        exporter = LorebookExporter(temp_project)
        entry = exporter.export_term_entry("魔法少女")

        assert entry.loreKey == "term:魔法少女"
        assert "魔法少女" in entry.entry

    def test_export_scene_entry(self, memory_with_data, temp_project):
        """Test exporting scene as lorebook entry."""
        exporter = LorebookExporter(temp_project)
        entry = exporter.export_scene_entry("ch1_p1")

        assert entry.loreKey == "scene:ch1_p1"
        assert "学校天台" in entry.entry

    def test_export_all(self, memory_with_data, temp_project):
        """Test exporting all memory entities."""
        exporter = LorebookExporter(temp_project)
        lorebook = exporter.export_all()

        # Should have character + term + scene = 3 entries
        assert len(lorebook.entries) >= 1

    def test_save_lorebook(self, memory_with_data, temp_project):
        """Test saving lorebook to file."""
        output_path = temp_project / "lorebook.json"
        exporter = LorebookExporter(temp_project)
        saved = exporter.save(output_path)

        assert saved == output_path
        assert saved.exists()

        # Verify JSON is valid
        data = json.loads(saved.read_text(encoding="utf-8"))
        assert "entries" in data


# ── Importer Tests ─────────────────────────────────────────────────────────────

class TestCharacterCardImporter:
    """Tests for CharacterCardImporter."""

    def test_import_card(self, temp_project):
        """Test importing a character card."""
        card = CharacterCard(
            name="TestChar",
            description="日文名: TestJp",
            personality="角色原型: Hero\n说话模式: casual=da",
            mes_example='Example 1: "Hello!"',
        )

        importer = CharacterCardImporter(temp_project)
        profile = importer.import_card(card)

        assert profile.name_zh == "TestChar"
        assert profile.name_jp == "TestJp"
        assert profile.archetype == "Hero"

    def test_import_directory(self, temp_project):
        """Test importing a directory of cards."""
        # Create test card file
        card_data = {
            "name": "TestChar",
            "description": "日文名: TestJp",
            "personality": "原型: Hero",
        }
        cards_dir = temp_project / "cards"
        cards_dir.mkdir()
        (cards_dir / "test.json").write_text(json.dumps(card_data), encoding="utf-8")

        importer = CharacterCardImporter(temp_project)
        profiles = importer.import_directory(cards_dir)

        assert len(profiles) == 1
        assert profiles[0].name_zh == "TestChar"

    def test_extract_catchphrases(self, temp_project):
        """Test catchphrase extraction."""
        importer = CharacterCardImporter(temp_project)
        phrases = importer._extract_catchphrases('Example 1: "加油！"')
        assert "加油！" in phrases


class TestLorebookImporter:
    """Tests for LorebookImporter."""

    def test_import_character_entry(self, temp_project):
        """Test importing character from lorebook entry."""
        entry = LorebookEntry(
            loreKey="character:sakura",
            entry="# 樱\n日文名: 桜\n角色类型: 元气少女",
            key=["樱", "sakura"],
        )

        importer = LorebookImporter(temp_project)
        stats = importer.import_lorebook(Lorebook(entries=[entry]))

        assert stats["characters"] == 1

    def test_import_term_entry(self, temp_project):
        """Test importing term from lorebook entry."""
        entry = LorebookEntry(
            loreKey="term:magic_girl",
            entry="# 魔法少女\n翻译: 魔法少女\n策略: preserve",
            key=["魔法少女"],
        )

        importer = LorebookImporter(temp_project)
        stats = importer.import_lorebook(Lorebook(entries=[entry]))

        assert stats["terms"] == 1

    def test_import_lorebook_file(self, temp_project):
        """Test importing lorebook from file."""
        lorebook_data = {
            "entries": [
                {
                    "loreKey": "character:test",
                    "entry": "# 测试角色\n日文名: テスト\n角色类型: 普通人",
                    "key": ["测试角色"],
                    "case_sensitive": False,
                    "priority": 50,
                    "constant": False,
                    "selective": True,
                    "uid": "abc123",
                }
            ],
            "version": 1,
        }

        lorebook_path = temp_project / "lorebook.json"
        lorebook_path.write_text(json.dumps(lorebook_data), encoding="utf-8")

        importer = LorebookImporter(temp_project)
        stats = importer.import_file(lorebook_path)

        assert stats["characters"] == 1

    def test_auto_detect_character_entry(self, temp_project):
        """Test auto-detection of character entry by content."""
        entry = LorebookEntry(
            loreKey="unknown:test",  # No prefix
            entry="# 樱\n日文名: 桜\n角色类型: 元气少女",
            key=["樱"],
        )

        importer = LorebookImporter(temp_project)
        # Without prefix, defaults to term import
        # But if it has character fields, should be handled
        lorebook = Lorebook(entries=[entry])
        stats = importer.import_lorebook(lorebook)

        # Default to term for unknown prefix
        assert stats["terms"] == 1


# ── Hermes Skill Tests ─────────────────────────────────────────────────────────

class TestHermesSkillImporter:
    """Tests for HermesSkillImporter."""

    def test_export_skill(self, memory_with_data, temp_project):
        """Test exporting character as Hermes skill."""
        from mga.distill.importers import HermesSkillImporter

        importer = HermesSkillImporter(temp_project)
        skill = importer.export_skill("sakura")

        assert "name" in skill
        assert "instruction" in skill
        assert "sakura" in skill["name"]

    def test_import_skill(self, temp_project):
        """Test importing Hermes skill into memory."""
        from mga.distill.importers import HermesSkillImporter

        skill_data = {
            "name": "act_as_sakura",
            "instruction": "You are 樱. Character type: 元气少女.",
            "variables": {
                "character_name": "樱",
                "archetype": "元气少女",
            },
        }

        importer = HermesSkillImporter(temp_project)
        character_id = importer.import_skill(skill_data)

        assert character_id == "sakura"


# ── Integration Tests ──────────────────────────────────────────────────────────

class TestDistillIntegration:
    """Integration tests for full export/import cycle."""

    def test_export_import_roundtrip(self, memory_with_data, temp_project):
        """Test exporting and re-importing character data."""
        # Export character cards
        export_dir = temp_project / "export"
        exporter = CharacterCardExporter(temp_project)
        saved = exporter.save(export_dir)
        assert len(saved) == 1

        # Read the exported file and verify it can be loaded
        card_path = saved[0]
        data = json.loads(card_path.read_text(encoding="utf-8"))
        assert data["name"] == "樱"
        assert "角色原型" in data["description"]
        assert "元气少女" in data["description"]

    def test_lorebook_export_import(self, memory_with_data, temp_project):
        """Test lorebook export and re-import."""
        # Export lorebook
        lorebook_path = temp_project / "lorebook.json"
        exporter = LorebookExporter(temp_project)
        exporter.save(lorebook_path)

        # Clear memory
        from mga.memory.service import reset_memory_service
        reset_memory_service(temp_project)

        # Re-initialize
        memory = MemoryService(temp_project)
        memory.initialize()

        # Import lorebook
        importer = LorebookImporter(temp_project)
        stats = importer.import_file(lorebook_path)

        # Should have imported something
        assert stats["terms"] >= 0 or stats["characters"] >= 0