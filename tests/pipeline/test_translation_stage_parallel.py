"""Tests for semantic-parallel translation stage routing."""

from __future__ import annotations

import threading
import pytest

from mga.memory.character_memory_updater import CharacterMemoryUpdater
from mga.models import (
    Bubble,
    Page,
    ProjectConfig,
    ProviderRoute,
    StageProviderConfig,
    TranslationCandidate,
)
from mga.pipeline.stages import PipelineContext
from mga.pipeline.translation_stage import TranslationStage


class SemanticParallelProvider:
    def chat(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        if prompt.startswith("## Semantic Translation"):
            source = prompt.rsplit("Source:", 1)[-1].splitlines()[0].strip()
            return (
                '{"text":"semantic:' + source + '","speech_act":"statement",'
                '"emotion":"calm","must_preserve":[],"footnotes":[],'
                '"rationale":"ok","confidence":0.9}'
            )
        return (
            '{"text":"final","persona_moves":["naturalize"],'
            '"rationale":"ok","confidence":0.9}'
        )


def test_translation_stage_semantic_parallel_mode_translates_page(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: SemanticParallelProvider(),
    )
    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={
                "parallel_mode": "semantic-parallel",
                "max_concurrent_requests": 2,
                "semantic_timeout": 30,
            },
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(bubble_id="b1", source_text="source one", reading_order=0),
                    Bubble(bubble_id="b2", source_text="source two", reading_order=1),
                ],
            )
        ],
    )

    result = TranslationStage().execute(ctx)

    assert [candidate.bubble_id for candidate in result.translations] == ["b1", "b2"]
    assert [candidate.text for candidate in result.translations] == ["final", "final"]
    artifact = result.artifacts["translation"]
    assert artifact["parallel_mode"] == "semantic-parallel"
    assert artifact["dialogue_realization"]["semantic_count"] == 2


def test_translation_stage_uses_project_parallel_mode_fallback(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: SemanticParallelProvider(),
    )
    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            parallel_mode="semantic-parallel",
            translation_max_workers=2,
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(bubble_id="b1", source_text="source one", reading_order=0),
                    Bubble(bubble_id="b2", source_text="source two", reading_order=1),
                ],
            )
        ],
    )

    result = TranslationStage().execute(ctx)

    assert [candidate.bubble_id for candidate in result.translations] == ["b1", "b2"]
    assert result.artifacts["translation"]["parallel_mode"] == "semantic-parallel"


def test_translation_stage_skips_non_renderable_vision_text(tmp_path, monkeypatch) -> None:
    calls: list[str] = []

    class RecordingProvider:
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            calls.append(prompt)
            if prompt.startswith("## Semantic Translation"):
                source = prompt.rsplit("Source:", 1)[-1].splitlines()[0].strip()
                return (
                    '{"text":"semantic:' + source + '","speech_act":"statement",'
                    '"emotion":"calm","must_preserve":[],"footnotes":[],'
                    '"rationale":"ok","confidence":0.9}'
                )
            return (
                '{"text":"final","persona_moves":["naturalize"],'
                '"rationale":"ok","confidence":0.9}'
            )

    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: RecordingProvider(),
    )
    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(
                        bubble_id="vision-0008-0000",
                        source_text="御子ちゃん",
                        detection_source="vision",
                        box_type="dialogue",
                        reading_order=0,
                    ),
                    Bubble(
                        bubble_id="vision-0008-0001",
                        source_text="ガタッ",
                        detection_source="vision",
                        box_type="sfx",
                        reading_order=1,
                    ),
                    Bubble(
                        bubble_id="vision-0008-0002",
                        source_text="7",
                        detection_source="vision",
                        box_type="other",
                        reading_order=2,
                    ),
                ],
            )
        ],
    )

    result = TranslationStage().execute(ctx)

    assert [candidate.bubble_id for candidate in result.translations] == ["vision-0008-0000"]
    joined_calls = "\n".join(calls)
    assert "御子ちゃん" in joined_calls
    assert "ガタッ" not in joined_calls
    assert "Source: 7" not in joined_calls


def test_translation_stage_allows_contents_page_vision_entries(tmp_path, monkeypatch) -> None:
    calls: list[str] = []

    class RecordingProvider:
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            calls.append(prompt)
            return (
                '{"text":"final","persona_moves":["naturalize"],'
                '"rationale":"ok","confidence":0.9}'
            )

    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: RecordingProvider(),
    )
    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(
                        bubble_id="vision-0003-0000",
                        source_text="CONTENTS",
                        detection_source="vision",
                        box_type="other",
                        reading_order=0,
                    ),
                    Bubble(
                        bubble_id="vision-0003-0001",
                        source_text="昔日の足音 003",
                        detection_source="vision",
                        box_type="other",
                        reading_order=1,
                    ),
                ],
            )
        ],
    )

    result = TranslationStage().execute(ctx)

    assert [candidate.bubble_id for candidate in result.translations] == [
        "vision-0003-0000",
        "vision-0003-0001",
    ]
    joined_calls = "\n".join(calls)
    assert "CONTENTS" in joined_calls
    assert "昔日の足音 003" in joined_calls


def test_semantic_parallel_skips_non_renderable_vision_text(tmp_path, monkeypatch) -> None:
    seen_sources: list[str] = []

    class RecordingProvider:
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if prompt.startswith("## Semantic Translation"):
                source = prompt.rsplit("Source:", 1)[-1].splitlines()[0].strip()
                seen_sources.append(source)
                return (
                    '{"text":"semantic:' + source + '","speech_act":"statement",'
                    '"emotion":"calm","must_preserve":[],"footnotes":[],'
                    '"rationale":"ok","confidence":0.9}'
                )
            return (
                '{"text":"final","persona_moves":["naturalize"],'
                '"rationale":"ok","confidence":0.9}'
            )

    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: RecordingProvider(),
    )
    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={
                "parallel_mode": "semantic-parallel",
                "max_concurrent_requests": 2,
                "semantic_timeout": 30,
            },
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(
                        bubble_id="vision-0008-0000",
                        source_text="御子ちゃん",
                        detection_source="vision",
                        box_type="dialogue",
                        reading_order=0,
                    ),
                    Bubble(
                        bubble_id="vision-0008-0001",
                        source_text="ガタッ",
                        detection_source="vision",
                        box_type="sfx",
                        reading_order=1,
                    ),
                ],
            )
        ],
    )

    result = TranslationStage().execute(ctx)

    assert [candidate.bubble_id for candidate in result.translations] == ["vision-0008-0000"]
    assert seen_sources == ["御子ちゃん"]
    assert result.artifacts["translation"]["dialogue_realization"]["semantic_count"] == 1


def test_fallback_to_serial_clears_contaminated_state(tmp_path, monkeypatch) -> None:
    """When parallel execution fails, fallback should clear partial state."""
    call_count = {"semantic_parallel": 0, "serial": 0}
    counter_lock = threading.Lock()

    class FallbackProvider:
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if prompt.startswith("## Semantic Translation"):
                with counter_lock:
                    call_count["semantic_parallel"] += 1
                    should_fail = call_count["semantic_parallel"] == 2
                if should_fail:
                    raise RuntimeError("Simulated parallel failure")
                return (
                    '{"text":"parallel_partial","speech_act":"statement",'
                    '"emotion":"calm","must_preserve":[],"footnotes":[],'
                    '"rationale":"ok","confidence":0.9}'
                )
            with counter_lock:
                call_count["serial"] += 1
            return (
                '{"text":"serial_clean","persona_moves":["naturalize"],'
                '"rationale":"ok","confidence":0.9}'
            )

    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: FallbackProvider(),
    )

    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={
                "parallel_mode": "semantic-parallel",
                "max_concurrent_requests": 2,
                "semantic_timeout": 30,
            },
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(bubble_id="b1", source_text="first", reading_order=0),
                    Bubble(bubble_id="b2", source_text="second", reading_order=1),
                    Bubble(bubble_id="b3", source_text="third", reading_order=2),
                ],
            )
        ],
    )

    ctx.translations = [TranslationCandidate(bubble_id="contaminated", text="old")]
    ctx.memory_context["character_profiles"] = {"fake_char": {"contaminated": True}}

    result = TranslationStage().execute(ctx)

    assert len(result.translations) == 3
    assert all(t.text == "serial_clean" for t in result.translations)
    assert not any(t.text == "parallel_partial" for t in result.translations)
    assert not any(t.bubble_id == "contaminated" for t in result.translations)
    assert "parallel_mode" not in result.artifacts["translation"]
    assert call_count["serial"] == 3


def test_semantic_parallel_multi_page_memory_consistency(tmp_path, monkeypatch) -> None:
    """Memory context should accumulate consistently across multiple pages."""
    memory_updates = []

    class MultiPageProvider:
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if prompt.startswith("## Semantic Translation"):
                source = prompt.rsplit("Source:", 1)[-1].splitlines()[0].strip()
                if "p1" in prompt:
                    return (
                        '{"text":"page1:' + source + '","speech_act":"statement",'
                        '"emotion":"calm","must_preserve":[],"footnotes":[],'
                        '"rationale":"ok","confidence":0.9}'
                    )
                return (
                    '{"text":"page2:' + source + '","speech_act":"statement",'
                    '"emotion":"calm","must_preserve":[],"footnotes":[],'
                    '"rationale":"ok","confidence":0.9}'
                )
            return (
                '{"text":"final","persona_moves":["naturalize"],'
                '"rationale":"ok","confidence":0.9}'
            )

    original_update = CharacterMemoryUpdater.update_from_translation

    def tracked_update(self, *args, **kwargs):
        memory_updates.append({"args": args, "kwargs": kwargs})
        return original_update(self, *args, **kwargs)

    monkeypatch.setattr(
        "mga.memory.character_memory_updater.CharacterMemoryUpdater.update_from_translation",
        tracked_update,
    )
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: MultiPageProvider(),
    )

    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={
                "parallel_mode": "semantic-parallel",
                "max_concurrent_requests": 2,
                "semantic_timeout": 30,
            },
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(
                        bubble_id="p1_b1",
                        source_text="page one text",
                        reading_order=0,
                        speaker_id="speaker",
                    ),
                    Bubble(
                        bubble_id="p1_b2",
                        source_text="more page one",
                        reading_order=1,
                        speaker_id="speaker",
                    ),
                ],
            ),
            Page(
                page_id="p2",
                bubbles=[
                    Bubble(
                        bubble_id="p2_b1",
                        source_text="page two text",
                        reading_order=0,
                        speaker_id="speaker",
                    ),
                    Bubble(
                        bubble_id="p2_b2",
                        source_text="more page two",
                        reading_order=1,
                        speaker_id="speaker",
                    ),
                ],
            ),
        ],
    )

    result = TranslationStage().execute(ctx)

    assert len(result.translations) == 4
    assert [t.bubble_id for t in result.translations] == ["p1_b1", "p1_b2", "p2_b1", "p2_b2"]
    assert "character_profiles" in result.memory_context
    assert "page_profiles" in result.memory_context
    assert len(memory_updates) >= 2, "Memory should update after each page"
    artifact = result.artifacts["translation"]
    assert artifact["dialogue_realization"]["semantic_count"] == 4
    assert artifact["parallel_mode"] == "semantic-parallel"


def test_fallback_to_serial_on_parallel_execution_error(tmp_path, monkeypatch) -> None:
    """Direct fallback test when semantic parallel execution raises ParallelExecutionError."""
    from mga.pipeline.parallel_executor import ParallelExecutionError

    serial_called = {"count": 0}

    class SerialProvider:
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            if prompt.startswith("## Semantic Translation"):
                return (
                    '{"text":"semantic","speech_act":"statement",'
                    '"emotion":"calm","must_preserve":[],"footnotes":[],'
                    '"rationale":"ok","confidence":0.9}'
                )
            serial_called["count"] += 1
            return (
                '{"text":"serial_fallback","persona_moves":[],'
                '"rationale":"ok","confidence":0.9}'
            )

    def failing_parallel_semantic(*args, **kwargs):
        raise ParallelExecutionError("Simulated parallel execution failure", errors=[])

    monkeypatch.setattr(
        "mga.pipeline.translation_stage.TranslationStage._parallel_semantic_translation",
        failing_parallel_semantic,
    )
    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: SerialProvider(),
    )

    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={
                "parallel_mode": "semantic-parallel",
                "max_concurrent_requests": 2,
            },
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(bubble_id="b1", source_text="text", reading_order=0),
                ],
            )
        ],
    )

    result = TranslationStage().execute(ctx)

    assert len(result.translations) == 1
    assert result.translations[0].text == "serial_fallback"
    assert serial_called["count"] == 1
    assert "parallel_mode" not in result.artifacts["translation"]


def test_multi_page_profile_propagation(tmp_path, monkeypatch) -> None:
    """Page 2 persona rendering should receive profiles updated from page 1."""
    prompts_received = []

    class ProfileTrackingProvider:
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            prompts_received.append(prompt)

            if prompt.startswith("## Semantic Translation"):
                return (
                    '{"text":"semantic","speech_act":"statement",'
                    '"emotion":"calm","must_preserve":[],"footnotes":[],'
                    '"rationale":"ok","confidence":0.9}'
                )
            return (
                '{"text":"final","persona_moves":[],'
                '"rationale":"ok","confidence":0.9}'
            )

    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: ProfileTrackingProvider(),
    )

    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={
                "parallel_mode": "semantic-parallel",
                "max_concurrent_requests": 2,
            },
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(
                        bubble_id="p1_b1",
                        source_text="hello",
                        reading_order=0,
                        speaker_id="alice",
                    ),
                ],
            ),
            Page(
                page_id="p2",
                bubbles=[
                    Bubble(
                        bubble_id="p2_b1",
                        source_text="world",
                        reading_order=0,
                        speaker_id="alice",
                    ),
                ],
            ),
        ],
    )

    result = TranslationStage().execute(ctx)

    assert len(result.translations) == 2
    page2_persona_prompts = [
        prompt
        for prompt in prompts_received
        if prompt.startswith("## Persona Rendering") and "Source: world" in prompt
    ]
    assert len(page2_persona_prompts) == 1

    page2_prompt = page2_persona_prompts[0]
    # Check that alice's profile is included (may be in various formats)
    assert "alice" in page2_prompt.lower()


def test_intra_page_memory_consistency(tmp_path, monkeypatch) -> None:
    """Bubble 2 persona rendering should see bubble 1 memory updates on the same page."""
    persona_prompts = []

    class SequenceTrackingProvider:
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]

            if prompt.startswith("## Semantic Translation"):
                return (
                    '{"text":"semantic","speech_act":"statement",'
                    '"emotion":"calm","must_preserve":[],"footnotes":[],'
                    '"rationale":"ok","confidence":0.9}'
                )

            if prompt.startswith("## Persona Rendering"):
                persona_prompts.append(prompt)

            return (
                '{"text":"final","persona_moves":[],'
                '"rationale":"ok","confidence":0.9}'
            )

    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: SequenceTrackingProvider(),
    )

    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={
                "parallel_mode": "semantic-parallel",
                "max_concurrent_requests": 2,
            },
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(
                        bubble_id="b1",
                        source_text="first",
                        reading_order=0,
                        speaker_id="bob",
                    ),
                    Bubble(
                        bubble_id="b2",
                        source_text="second",
                        reading_order=1,
                        speaker_id="bob",
                    ),
                ],
            )
        ],
    )

    result = TranslationStage().execute(ctx)

    assert len(persona_prompts) == 2

    bubble2_prompt = persona_prompts[1]
    assert "bob" in bubble2_prompt.lower()

    assert "character_profiles" in result.memory_context
    assert "bob" in result.memory_context["character_profiles"]


def test_fallback_preserves_memory_integrity(tmp_path, monkeypatch) -> None:
    """Memory profiles should not leak between parallel failure and serial retry."""
    state_dir = tmp_path / "memory" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    character_state_file = state_dir / "characters.json"
    character_state_file.write_text('{"characters": []}')

    call_sequence = []
    sequence_lock = threading.Lock()

    class MemoryTrackingProvider:
        def chat(self, messages, **kwargs):
            prompt = messages[-1]["content"]
            has_profile = "## 角色档案" in prompt
            mode = "semantic" if prompt.startswith("## Semantic Translation") else "persona"
            with sequence_lock:
                call_sequence.append({
                    "mode": mode,
                    "has_profile": has_profile,
                })
                should_fail = mode == "semantic" and len(
                    [c for c in call_sequence if c["mode"] == "semantic"]
                ) == 2

            if prompt.startswith("## Semantic Translation"):
                if should_fail:
                    raise RuntimeError("Parallel failure")
                return (
                    '{"text":"semantic","speech_act":"statement",'
                    '"emotion":"calm","must_preserve":[],"footnotes":[],'
                    '"rationale":"ok","confidence":0.9}'
                )
            return (
                '{"text":"final","persona_moves":["naturalize"],'
                '"rationale":"ok","confidence":0.9}'
            )

    monkeypatch.setattr(
        "mga.providers.cascade.get_provider",
        lambda name, **settings: MemoryTrackingProvider(),
    )

    ctx = PipelineContext(
        project_config=ProjectConfig(
            working_dir=str(tmp_path),
            target_lang="zh-CN",
            translation_config={
                "parallel_mode": "semantic-parallel",
                "max_concurrent_requests": 2,
                "semantic_timeout": 30,
            },
            provider_routes={
                "translation": StageProviderConfig(primary=ProviderRoute(provider="fake")),
            },
        ),
        pages=[
            Page(
                page_id="p1",
                bubbles=[
                    Bubble(bubble_id="b1", source_text="first", reading_order=0),
                    Bubble(bubble_id="b2", source_text="second", reading_order=1),
                ],
            )
        ],
    )

    ctx.memory_context["character_profiles"] = {
        "TestChar": {"voice": "contaminated_from_parallel"}
    }

    result = TranslationStage().execute(ctx)

    serial_calls = [c for c in call_sequence if c["mode"] == "persona"]

    assert len(serial_calls) == 2
    assert len(result.translations) == 2
    assert all(t.text == "final" for t in result.translations)
    if result.memory_context.get("character_profiles"):
        for profile in result.memory_context["character_profiles"].values():
            assert "contaminated_from_parallel" not in str(profile)
