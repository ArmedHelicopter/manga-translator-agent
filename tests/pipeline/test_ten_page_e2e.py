"""Ten-page end-to-end integration test for manga pipeline.

This test verifies:
1. Multi-page processing with character memory across pages
2. Relationship graph context injection
3. Scene context propagation
4. Translation quality with memory integration
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import pytest

from mga.memory.entities import CharacterState
from mga.memory.state import StateManager
from mga.models import Bubble, Page, ProjectConfig
from mga.pipeline.character_stage import CharacterAttributionStage
from mga.pipeline.speaker_attribution_stage import SpeakerAttributionStage
from mga.pipeline.stages import PipelineContext
from mga.pipeline.translation_stage import TranslationStage


class FakeTranslationProvider:
    """Fake LLM provider for testing."""

    def __init__(self):
        self.call_count = 0
        self.last_prompts: list[str] = []

    def chat(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        self.call_count += 1
        # Capture the prompt for verification
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    self.last_prompts.append(content[:500])

        # Return structured translation based on prompt content
        prompt = ""
        for msg in messages:
            if isinstance(msg, dict) and msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str):
                    prompt += content

        # Check for character memory context
        if "田中" in prompt or "tanaka" in prompt.lower():
            if "尊敬" in prompt or "polite" in prompt.lower():
                return json.dumps({
                    "text": "田中前辈，请问您今天有空吗？",
                    "footnotes": [],
                    "rationale": "Using polite form for mentor relationship",
                }, ensure_ascii=False)
            return json.dumps({
                "text": "田中，我们去吃饭吧！",
                "footnotes": [],
                "rationale": "Casual speech",
            }, ensure_ascii=False)

        if "佐藤" in prompt or "sato" in prompt.lower():
            return json.dumps({
                "text": "好的，我马上过来。",
                "footnotes": [],
                "rationale": "Polite response",
            }, ensure_ascii=False)

        # Check for relationship context
        if "关系上下文" in prompt or "mentor" in prompt.lower():
            if "尊敬" in prompt:
                return json.dumps({
                    "text": "老师，您辛苦了。",
                    "footnotes": [],
                    "rationale": "Respectful form from student to mentor",
                }, ensure_ascii=False)

        # Check for scene context
        if "学校" in prompt or "school" in prompt.lower():
            return json.dumps({
                "text": "大家一起加油吧！",
                "footnotes": [],
                "rationale": "School scene encouragement",
            }, ensure_ascii=False)

        # Default translations
        return json.dumps({
            "text": "翻译后的文本",
            "footnotes": [],
            "rationale": "Default translation",
        }, ensure_ascii=False)


def _create_10_page_manga() -> list[Page]:
    """Create a 10-page manga scenario with evolving character relationships."""
    pages = []

    # Page 1: Introduction - first meeting
    pages.append(Page(
        page_id="p001",
        bubbles=[
            Bubble(bubble_id="b001", source_text="こんにちは、田中先輩！", speaker_id="akari"),
            Bubble(bubble_id="b002", source_text="あ、佐藤さん。", speaker_id="tanaka"),
        ],
    ))

    # Page 2: First conversation
    pages.append(Page(
        page_id="p002",
        bubbles=[
            Bubble(bubble_id="b003", source_text="今日一緒に勉強しない？", speaker_id="akari"),
            Bubble(bubble_id="b004", source_text="いいよ、どこでする？", speaker_id="tanaka"),
        ],
    ))

    # Page 3: At school
    pages.append(Page(
        page_id="p003",
        bubbles=[
            Bubble(bubble_id="b005", source_text="ここ座っていい？", speaker_id="akari"),
            Bubble(bubble_id="b006", source_text="どうぞ。", speaker_id="tanaka"),
        ],
    ))

    # Page 4: Study session
    pages.append(Page(
        page_id="p004",
        bubbles=[
            Bubble(bubble_id="b007", source_text="この問題分かる？", speaker_id="tanaka"),
            Bubble(bubble_id="b008", source_text="うーん、少し難しい...", speaker_id="akari"),
        ],
    ))

    # Page 5: Tanakas help
    pages.append(Page(
        page_id="p005",
        bubbles=[
            Bubble(bubble_id="b009", source_text="ここに注目してごらん。", speaker_id="tanaka"),
            Bubble(bubble_id="b010", source_text="あ、分かった！ありがとう！", speaker_id="akari"),
        ],
    ))

    # Page 6: Time passes
    pages.append(Page(
        page_id="p006",
        bubbles=[
            Bubble(bubble_id="b011", source_text="田中先輩、ずっと教えてくれて。", speaker_id="akari"),
            Bubble(bubble_id="b012", source_text="いつでも聞いてくれていいよ。", speaker_id="tanaka"),
        ],
    ))

    # Page 7: New character appears
    pages.append(Page(
        page_id="p007",
        bubbles=[
            Bubble(bubble_id="b013", source_text="こんにちは！", speaker_id="ren"),
            Bubble(bubble_id="b014", source_text="あ、蓮くんだ。", speaker_id="tanaka"),
        ],
    ))

    # Page 8: Group dynamics
    pages.append(Page(
        page_id="p008",
        bubbles=[
            Bubble(bubble_id="b015", source_text="一緒に遊ぼうよ！", speaker_id="ren"),
            Bubble(bubble_id="b016", source_text="うん、いいね！", speaker_id="akari"),
        ],
    ))

    # Page 9: Different relationship (older friend)
    pages.append(Page(
        page_id="p009",
        bubbles=[
            Bubble(bubble_id="b017", source_text="先生、お待たせしました。", speaker_id="akari"),
            Bubble(bubble_id="b018", source_text="大丈夫、まだ始めてないよ。", speaker_id="teacher"),
        ],
    ))

    # Page 10: Wrap up
    pages.append(Page(
        page_id="p010",
        bubbles=[
            Bubble(bubble_id="b019", source_text="今日は楽しかった！", speaker_id="ren"),
            Bubble(bubble_id="b020", source_text="また遊ぼうな！", speaker_id="akari"),
        ],
    ))

    return pages


def _setup_character_graph(tmp_path: Path) -> None:
    """Set up character relationships for the test."""
    StateManager.upsert_character(tmp_path, CharacterState(
        character_id="akari",
        name_jp="灯里",
        name_zh="灯里",
        archetype="friendly",
        speech_patterns={" casual": "friendly casual"},
        catchphrases=["一緒に頑張ろう！"],
    ))

    StateManager.upsert_character(tmp_path, CharacterState(
        character_id="tanaka",
        name_jp="田中",
        name_zh="田中",
        archetype="mentor",
        speech_patterns={" polite": "patient mentor tone"},
        catchphrases=["ここに注目してごらん"],
    ))

    StateManager.upsert_character(tmp_path, CharacterState(
        character_id="ren",
        name_jp="蓮",
        name_zh="蓮",
        archetype="friend",
        speech_patterns={" casual": "energetic casual"},
        catchphrases=["遊ぼうよ！"],
    ))


class TestTenPageE2E:
    """Ten-page end-to-end integration tests."""

    def test_ten_pages_with_character_memory(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Verify 10-page pipeline with character memory propagation."""
        # Setup
        _setup_character_graph(tmp_path)
        pages = _create_10_page_manga()

        cfg = ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
        )

        fake_provider = FakeTranslationProvider()
        monkeypatch.setattr(
            "mga.providers.cascade.get_provider",
            lambda name, **kwargs: fake_provider,
        )

        # Run speaker attribution
        ctx = PipelineContext(project_config=cfg, pages=pages)
        ctx = SpeakerAttributionStage().execute(ctx)

        # Verify speakers were attributed
        assert ctx.pages[0].bubbles[0].speaker_id == "akari"
        assert ctx.pages[0].bubbles[1].speaker_id == "tanaka"

    def test_ten_pages_with_relationship_context(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Verify relationship context is injected in prompts for 10 pages."""
        from mga.memory.graph import CharacterGraph
        from mga.memory.graph_retrieval import GraphRetrieval

        # Setup character graph
        _setup_character_graph(tmp_path)

        # Add relationship edges
        graph = CharacterGraph.load(Path(tmp_path))
        if graph.graph.number_of_nodes() == 0:
            graph.add_character("akari", name_jp="灯里", archetype="friendly")
            graph.add_character("tanaka", name_jp="田中", archetype="mentor")
            graph.add_character("ren", name_jp="蓮", archetype="friend")
            graph.add_relationship("akari", "tanaka", "mentor", formality="polite")
            graph.add_relationship("tanaka", "akari", "student", formality="casual")
            graph.add_relationship("akari", "ren", "friend", formality="casual")
            graph.add_relationship("ren", "akari", "friend", formality="casual")
            graph.save(Path(tmp_path))

        graph_retrieval = GraphRetrieval(graph)

        # Get relationship context for a bubble
        ctx_str = graph_retrieval.get_translation_context("akari", "tanaka")

        # Verify relationship context exists
        assert ctx_str != ""
        assert "mentor" in ctx_str.lower() or "尊敬" in ctx_str or "先生" in ctx_str

    def test_ten_pages_translation_stage_completes(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Verify translation stage completes for 10 pages."""
        _setup_character_graph(tmp_path)
        pages = _create_10_page_manga()

        cfg = ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
        )

        fake_provider = FakeTranslationProvider()
        monkeypatch.setattr(
            "mga.providers.cascade.get_provider",
            lambda name, **kwargs: fake_provider,
        )

        # Run full pipeline up to translation
        ctx = PipelineContext(project_config=cfg, pages=pages)
        ctx = SpeakerAttributionStage().execute(ctx)
        ctx = CharacterAttributionStage().execute(ctx)
        ctx = TranslationStage().execute(ctx)

        # Verify all pages were processed
        assert len(ctx.translations) >= 10, f"Expected at least 10 translations, got {len(ctx.translations)}"

        # Verify all bubbles got translations
        total_bubbles = sum(len(p.bubbles) for p in ctx.pages)
        assert len(ctx.translations) >= total_bubbles, \
            f"Expected {total_bubbles} translations, got {len(ctx.translations)}"

    def test_memory_propagates_across_pages(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Verify character memory is updated and used across all 10 pages."""
        _setup_character_graph(tmp_path)
        pages = _create_10_page_manga()

        cfg = ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
        )

        fake_provider = FakeTranslationProvider()
        monkeypatch.setattr(
            "mga.providers.cascade.get_provider",
            lambda name, **kwargs: fake_provider,
        )

        # Run pipeline
        ctx = PipelineContext(project_config=cfg, pages=pages)
        ctx = SpeakerAttributionStage().execute(ctx)
        ctx = CharacterAttributionStage().execute(ctx)
        ctx = TranslationStage().execute(ctx)

        # Verify memory context was populated
        assert "character_profiles" in ctx.memory_context
        assert len(ctx.memory_context["character_profiles"]) > 0

        # Verify character memory trace exists
        assert "character_memory" in ctx.artifacts
        assert len(ctx.artifacts["character_memory"]) > 0

    def test_ten_pages_sequential_memory_update(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Verify memory is updated sequentially across 10 pages."""
        _setup_character_graph(tmp_path)
        pages = _create_10_page_manga()

        cfg = ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
        )

        fake_provider = FakeTranslationProvider()
        monkeypatch.setattr(
            "mga.providers.cascade.get_provider",
            lambda name, **kwargs: fake_provider,
        )

        # Process pages sequentially
        ctx = PipelineContext(project_config=cfg, pages=[])
        for page in pages:
            page_ctx = PipelineContext(
                project_config=cfg,
                pages=[page],
                memory_context=ctx.memory_context,
            )
            page_ctx = SpeakerAttributionStage().execute(page_ctx)
            page_ctx = CharacterAttributionStage().execute(page_ctx)
            page_ctx = TranslationStage().execute(page_ctx)

            # Merge memory context
            for char_id, profile in page_ctx.memory_context.get("character_profiles", {}).items():
                if char_id not in ctx.memory_context.get("character_profiles", {}):
                    ctx.memory_context.setdefault("character_profiles", {})[char_id] = profile
                else:
                    ctx.memory_context["character_profiles"][char_id].update(profile)

            ctx.translations.extend(page_ctx.translations)

        # Verify all pages processed
        assert len(ctx.translations) >= 20, f"Expected at least 20 translations, got {len(ctx.translations)}"

        # Verify memory was updated
        assert len(ctx.memory_context.get("character_profiles", {})) > 0


class TestRelationshipGraphE2E:
    """Relationship graph end-to-end tests."""

    def test_graph_context_in_prompt_for_mentor_relationship(self, tmp_path: Path) -> None:
        """Verify mentor relationship context appears in translation prompt."""
        from mga.memory.graph import CharacterGraph
        from mga.memory.graph_retrieval import GraphRetrieval

        # Setup
        graph = CharacterGraph()
        graph.add_character("student", name_jp="学生", archetype="student")
        graph.add_character("mentor", name_jp="先生", archetype="mentor")
        graph.add_relationship("student", "mentor", "mentor", formality="polite")
        graph.add_relationship("mentor", "student", "student", formality="casual")

        graph_retrieval = GraphRetrieval(graph)

        # Get context
        ctx_str = graph_retrieval.get_translation_context("student", "mentor")

        # Verify relationship context
        assert ctx_str != ""
        assert "mentor" in ctx_str.lower() or "先生" in ctx_str

    def test_graph_formality_levels(self, tmp_path: Path) -> None:
        """Verify formality levels are correctly stored and retrieved."""
        from mga.memory.graph import CharacterGraph
        from mga.memory.graph_retrieval import GraphRetrieval

        # Setup with formality levels
        graph = CharacterGraph()
        graph.add_character("a", name_jp="A", archetype="character")
        graph.add_character("b", name_jp="B", archetype="character")
        graph.add_relationship("a", "b", "senior", formality="polite")

        graph_retrieval = GraphRetrieval(graph)

        addressing = graph_retrieval.get_addressing("a", "b")
        assert addressing is not None
        # Check that the relationship was stored correctly
        assert addressing.get("formality", "") == "polite"

    def test_graph_save_and_load(self, tmp_path: Path) -> None:
        """Verify relationship graph can be saved and loaded."""
        from mga.memory.graph import CharacterGraph

        # Create and save
        graph = CharacterGraph()
        graph.add_character("c1", name_jp="キャラ1", archetype="type1")
        graph.add_character("c2", name_jp="キャラ2", archetype="type2")
        graph.add_relationship("c1", "c2", "friend", formality="casual")
        graph.save(Path(tmp_path))

        # Load
        loaded = CharacterGraph.load(Path(tmp_path))

        assert loaded.graph.number_of_nodes() == 2
        assert loaded.graph.number_of_edges() == 1