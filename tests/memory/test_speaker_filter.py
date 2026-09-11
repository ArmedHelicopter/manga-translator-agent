"""Tests for speaker ID filtering and canonicalisation.

Three acceptance criteria from docs/handoff-2026-06-22-memory-reassessment.md:
  (a) descriptive/placeholder hints are rejected (not persisted as characters)
  (b) same-character variant descriptions merge to one canonical id
  (c) real names still create characters normally
"""

from __future__ import annotations

from pathlib import Path

from mga.memory.character_memory_updater import CharacterMemoryUpdater
from mga.memory.entities import CharacterState
from mga.memory.speaker_filter import (
    build_token_index,
    extract_name_tokens,
    find_canonical_match,
    is_generic_speaker,
    pick_canonical_id,
)
from mga.memory.state import StateManager
from mga.models import Bubble, Page, ProjectConfig
from mga.pipeline.speaker_attribution_stage import SpeakerAttributionStage
from mga.pipeline.stages import PipelineContext


# ── (a) Descriptive / placeholder hints rejected ─────────────────────


class TestGenericSpeakerRejection:
    """Generic/trash speaker IDs must be rejected so they don't pollute memory."""

    def test_bare_generics_rejected(self):
        for label in [
            "unknown", "unidentified", "someone", "person", "speaker",
            "girl", "boy", "man", "woman", "child", "character",
            "female", "male", "narrator", "environmental", "environment",
            "none", "null", "n/a", "na", "n_a",
        ]:
            assert is_generic_speaker(label), f"Expected generic: {label!r}"

    def test_japanese_generics_rejected(self):
        for label in ["未確定", "未明確", "語り手", "登場人物"]:
            assert is_generic_speaker(label), f"Expected generic: {label!r}"

    def test_descriptive_phrases_rejected(self):
        for label in [
            "Girl with hand to mouth",
            "Girl in close-up",
            "Female character",
            "Male character",
            "Character with glasses",
            "Character (bottom-left panel, facing forward)",
            "Unseen speaker",
            "Off-screen speaker",
            "Offscreen speaker",
            "Background speaker",
            "Light-haired girl",
            "Dark-haired boy",
            "Girl with dark hair",
            "someone near the door",
            "girl-near-door",
            "girl-left",
            "girl-right",
            "N/A (environmental)",
        ]:
            assert is_generic_speaker(label), f"Expected generic: {label!r}"

    def test_descriptive_with_name_not_rejected(self):
        """A descriptive label that contains a real name in parens is NOT generic."""
        assert not is_generic_speaker("Girl with dark hair (Miho)")
        assert not is_generic_speaker("Light-haired girl (calling Miho)")
        assert not is_generic_speaker("Character (美胡)")

    def test_real_names_not_rejected(self):
        for label in ["美胡", "Miku", "akari", "灯里", "友人", "Miko"]:
            assert not is_generic_speaker(label), f"Expected NOT generic: {label!r}"

    def test_empty_and_none_rejected(self):
        assert is_generic_speaker("")
        assert is_generic_speaker(None)  # type: ignore[arg-type]


# ── (b) Same-character variants merge to one id ─────────────────────


class TestVariantMerging:
    """Variant descriptions of the same character must merge to one canonical id."""

    def test_extract_name_tokens_cjk_and_latin(self):
        tokens = extract_name_tokens("Miko (美胡)")
        assert "美胡" in tokens
        assert "miko" in tokens

    def test_extract_name_tokens_underscore_composite(self):
        tokens = extract_name_tokens("miko_美胡_the_girl_with_long_hair")
        assert "美胡" in tokens
        assert "miko" in tokens
        # Generic words filtered out
        assert "girl" not in tokens
        assert "hair" not in tokens

    def test_extract_name_tokens_honorific_stripped(self):
        tokens = extract_name_tokens("美胡ちゃん (Miko-chan)")
        assert "美胡" in tokens
        assert "miko" in tokens
        assert "ちゃん" not in tokens

    def test_extract_name_tokens_parenthetical_name(self):
        tokens = extract_name_tokens("Girl with dark hair (Miho)")
        assert "miho" in tokens
        # Generic words filtered out
        assert "girl" not in tokens
        assert "dark" not in tokens
        assert "hair" not in tokens

    def test_extract_name_tokens_no_tokens_for_generic(self):
        assert extract_name_tokens("Narrator") == set()
        assert extract_name_tokens("Female character") == set()
        assert extract_name_tokens("Unseen speaker") == set()

    def test_find_canonical_match_by_cjk_token(self):
        """Miko (美胡) matches existing character 美胡 via shared CJK token."""
        characters = [
            CharacterState(character_id="美胡", name_jp="美胡", name_zh="美胡"),
        ]
        index = build_token_index(characters)
        assert find_canonical_match("Miko (美胡)", index) == "美胡"
        assert find_canonical_match("miko_美胡_the_girl_with_long_hair", index) == "美胡"
        assert find_canonical_match("美胡ちゃん (Miko-chan)", index) == "美胡"

    def test_find_canonical_match_by_latin_token(self):
        """Miku (thought) matches existing character Miku via shared Latin token."""
        characters = [
            CharacterState(character_id="miku", name_jp="Miku", name_zh="Miku"),
        ]
        index = build_token_index(characters)
        assert find_canonical_match("Miku (thought)", index) == "miku"

    def test_find_canonical_match_no_match(self):
        characters = [
            CharacterState(character_id="美胡", name_jp="美胡", name_zh="美胡"),
        ]
        index = build_token_index(characters)
        assert find_canonical_match("友人", index) is None
        assert find_canonical_match("Narrator", index) is None

    def test_pick_canonical_id_prefers_cjk(self):
        assert pick_canonical_id("Miko (美胡)") == "美胡"
        assert pick_canonical_id("miko_美胡_the_girl_with_long_hair") == "美胡"
        assert pick_canonical_id("美胡ちゃん (Miko-chan)") == "美胡"

    def test_pick_canonical_id_latin_fallback(self):
        assert pick_canonical_id("Miku") == "miku"
        assert pick_canonical_id("akari") == "akari"

    def test_pick_canonical_id_fallback_no_tokens(self):
        """If no name tokens are extractable, fall back to normalised label."""
        assert pick_canonical_id("Narrator") == "narrator"

    def test_variants_merge_via_speaker_attribution(self, tmp_path):
        """Multiple variant descriptions on different pages canonicalise to one id.

        Speaker_attribution canonicalises the speaker_id but does not create
        characters for vision-set IDs (that is the updater's job).  This test
        verifies both pages end up with the same canonical speaker_id.
        """
        stage = SpeakerAttributionStage()
        # Page 1: vision sets speaker_id to "Miko (美胡)"
        page1 = Page(
            page_id="p001",
            bubbles=[
                Bubble(
                    bubble_id="b1",
                    source_text="こんにちは。",
                    speaker_id="Miko (美胡)",
                ),
            ],
        )
        ctx1 = PipelineContext(
            project_config=ProjectConfig(working_dir=str(tmp_path)),
            pages=[page1],
        )
        stage.execute(ctx1)

        # Page 2: vision sets speaker_id to "miko_美胡_the_girl_with_long_hair"
        page2 = Page(
            page_id="p002",
            bubbles=[
                Bubble(
                    bubble_id="b2",
                    source_text="またね。",
                    speaker_id="miko_美胡_the_girl_with_long_hair",
                ),
            ],
        )
        ctx2 = PipelineContext(
            project_config=ProjectConfig(working_dir=str(tmp_path)),
            pages=[page2],
        )
        stage.execute(ctx2)

        # Both bubbles should have the same canonical speaker_id
        assert ctx1.pages[0].bubbles[0].speaker_id == "美胡"
        assert ctx2.pages[0].bubbles[0].speaker_id == "美胡"

    def test_generic_vision_speaker_id_cleared(self, tmp_path):
        """Generic speaker_id set by vision is cleared, not persisted."""
        page = Page(
            page_id="p001",
            bubbles=[
                Bubble(
                    bubble_id="b1",
                    source_text="...",
                    speaker_id="Female character",
                ),
                Bubble(
                    bubble_id="b2",
                    source_text="...",
                    speaker_id="Narrator",
                ),
            ],
        )
        ctx = PipelineContext(
            project_config=ProjectConfig(working_dir=str(tmp_path)),
            pages=[page],
        )
        result = SpeakerAttributionStage().execute(ctx)

        assert result.pages[0].bubbles[0].speaker_id is None
        assert result.pages[0].bubbles[1].speaker_id is None
        assert StateManager.list_characters(tmp_path) == []


# ── (c) Real names still create characters ──────────────────────────


class TestRealNamesStillCreate:
    """Real character names must still create characters normally."""

    def test_cjk_name_creates_character(self, tmp_path):
        page = Page(
            page_id="p001",
            bubbles=[
                Bubble(bubble_id="b1", source_text="こんにちは。", provisional_speaker="美胡"),
            ],
        )
        ctx = PipelineContext(
            project_config=ProjectConfig(working_dir=str(tmp_path)),
            pages=[page],
        )
        SpeakerAttributionStage().execute(ctx)

        characters = StateManager.list_characters(tmp_path)
        assert len(characters) == 1
        assert characters[0].character_id == "美胡"

    def test_latin_name_creates_character(self, tmp_path):
        page = Page(
            page_id="p001",
            bubbles=[
                Bubble(bubble_id="b1", source_text="Hello.", provisional_speaker="Miku"),
            ],
        )
        ctx = PipelineContext(
            project_config=ProjectConfig(working_dir=str(tmp_path)),
            pages=[page],
        )
        SpeakerAttributionStage().execute(ctx)

        characters = StateManager.list_characters(tmp_path)
        assert len(characters) == 1
        assert characters[0].character_id == "miku"

    def test_existing_name_not_fragmented(self, tmp_path):
        """A real name that matches an existing character does not create a duplicate."""
        StateManager.upsert_character(
            tmp_path,
            CharacterState(character_id="akari", name_jp="灯里", name_zh="灯里"),
        )
        page = Page(
            page_id="p001",
            bubbles=[
                Bubble(bubble_id="b1", source_text="おはよう。", provisional_speaker="灯里"),
                Bubble(bubble_id="b2", source_text="またね。", provisional_speaker="灯里"),
            ],
        )
        ctx = PipelineContext(
            project_config=ProjectConfig(working_dir=str(tmp_path)),
            pages=[page],
        )
        SpeakerAttributionStage().execute(ctx)

        characters = StateManager.list_characters(tmp_path)
        assert len(characters) == 1, (
            f"Expected 1 character, got {len(characters)}"
        )


# ── CharacterMemoryUpdater safety net ───────────────────────────────


class TestUpdaterGenericFilter:
    """The updater must not persist generic/trash speaker IDs."""

    def test_updater_skips_generic_speaker(self, tmp_path):
        updater = CharacterMemoryUpdater(tmp_path)
        bubble = Bubble(
            bubble_id="b1",
            speaker_id="Narrator",
            source_text="語り。",
        )
        result = updater.update_from_translation(
            speaker="Narrator",
            bubble=bubble,
            page_id="p001",
            translated_text="旁白。",
            memory_before={},
            prompt="test",
        )
        assert result.memory_after == {}
        assert StateManager.list_characters(tmp_path) == []

    def test_updater_skips_descriptive_speaker(self, tmp_path):
        updater = CharacterMemoryUpdater(tmp_path)
        bubble = Bubble(
            bubble_id="b1",
            speaker_id="Female character",
            source_text="...",
        )
        updater.update_from_translation(
            speaker="Female character",
            bubble=bubble,
            page_id="p001",
            translated_text="...",
            memory_before={},
            prompt="test",
        )
        assert StateManager.list_characters(tmp_path) == []

    def test_updater_canonicalises_variant_to_existing(self, tmp_path):
        """When the updater receives a variant ID, it merges with existing character."""
        # Pre-existing character created by speaker_attribution
        StateManager.upsert_character(
            tmp_path,
            CharacterState(
                character_id="美胡",
                name_jp="美胡",
                name_zh="美胡",
                provenance={"source": "cold_start_speaker_hint"},
            ),
        )
        updater = CharacterMemoryUpdater(tmp_path)
        bubble = Bubble(
            bubble_id="b1",
            speaker_id="Miko (美胡)",
            source_text="こんにちは。",
        )
        updater.update_from_translation(
            speaker="Miko (美胡)",
            bubble=bubble,
            page_id="p001",
            translated_text="你好。",
            memory_before={},
            prompt="test",
        )
        characters = StateManager.list_characters(tmp_path)
        assert len(characters) == 1, (
            f"Expected 1 character, got {len(characters)}: "
            f"{[c.character_id for c in characters]}"
        )
        assert characters[0].character_id == "美胡"
        # The variant should be recorded as an alias for future matching
        aliases = characters[0].provenance.get("aliases", [])
        assert "Miko (美胡)" in aliases

    def test_updater_creates_with_clean_id(self, tmp_path):
        """When the updater creates a new character, it uses a clean canonical ID."""
        updater = CharacterMemoryUpdater(tmp_path)
        bubble = Bubble(
            bubble_id="b1",
            speaker_id="Miko (美胡)",
            source_text="こんにちは。",
        )
        updater.update_from_translation(
            speaker="Miko (美胡)",
            bubble=bubble,
            page_id="p001",
            translated_text="你好。",
            memory_before={},
            prompt="test",
        )
        characters = StateManager.list_characters(tmp_path)
        assert len(characters) == 1
        assert characters[0].character_id == "美胡"
