"""Test-only harness for proving cross-page character memory flow.

This module intentionally stays outside production ``mga`` code. It gives the
tests a deterministic research harness for:

speaker_id -> memory update -> prompt injection -> fake style-conditioned output
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from mga.memory.entities import CharacterState
from mga.memory.profile_loader import get_profile_as_dict
from mga.memory.state import StateManager
from mga.pipeline.translation_stage import _build_translation_prompt


@dataclass(frozen=True)
class DemoBubbleTrace:
    page_id: str
    bubble_id: str
    speaker_id: str
    source_text: str
    prompt: str
    translation: str
    memory_before: dict[str, Any]


@dataclass(frozen=True)
class CharacterMemorySnapshot:
    page_id: str
    speaker_id: str
    evidence_lines: tuple[str, ...]
    style_summary: str
    last_updated_page: str
    prompt_excerpt: str


@dataclass(frozen=True)
class CharacterMemoryDemoResult:
    traces: list[DemoBubbleTrace] = field(default_factory=list)
    snapshots: list[CharacterMemorySnapshot] = field(default_factory=list)

    def trace_for(self, bubble_id: str) -> DemoBubbleTrace:
        for trace in self.traces:
            if trace.bubble_id == bubble_id:
                return trace
        raise KeyError(bubble_id)

    def snapshot_for(self, page_id: str, speaker_id: str) -> CharacterMemorySnapshot:
        for snapshot in self.snapshots:
            if snapshot.page_id == page_id and snapshot.speaker_id == speaker_id:
                return snapshot
        raise KeyError(f"{page_id}:{speaker_id}")


def run_character_memory_demo(fixture_path: Path, project_dir: Path) -> CharacterMemoryDemoResult:
    """Run a deterministic fixture-level character-memory demo."""

    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    traces: list[DemoBubbleTrace] = []
    snapshots: list[CharacterMemorySnapshot] = []

    for page in data["pages"]:
        page_id = page["page_id"]
        touched_speakers: set[str] = set()

        for bubble in page["bubbles"]:
            speaker_id = bubble["speaker_id"]
            source_text = bubble["source_text"]
            bubble_id = bubble["bubble_id"]
            profile = StateManager.get_character(project_dir, speaker_id)
            memory_before = get_profile_as_dict(profile) if profile else {}
            prompt = _build_translation_prompt(source_text, memory_before, {}, "zh")
            translation = _fake_translate(prompt)

            traces.append(
                DemoBubbleTrace(
                    page_id=page_id,
                    bubble_id=bubble_id,
                    speaker_id=speaker_id,
                    source_text=source_text,
                    prompt=prompt,
                    translation=translation,
                    memory_before=memory_before,
                )
            )

            _update_profile_from_observation(
                project_dir=project_dir,
                speaker_id=speaker_id,
                page_id=page_id,
                source_text=source_text,
                translated_text=translation,
            )
            touched_speakers.add(speaker_id)

        for speaker_id in sorted(touched_speakers):
            profile = StateManager.get_character(project_dir, speaker_id)
            if profile is not None:
                snapshots.append(_snapshot_for(page_id, profile, traces))

    return CharacterMemoryDemoResult(traces=traces, snapshots=snapshots)


def _load_or_create_profile(project_dir: Path, speaker_id: str) -> CharacterState:
    profile = StateManager.get_character(project_dir, speaker_id)
    if profile is None:
        profile = CharacterState(character_id=speaker_id, name_jp=speaker_id)
        StateManager.upsert_character(project_dir, profile)
    return profile


def _update_profile_from_observation(
    project_dir: Path,
    speaker_id: str,
    page_id: str,
    source_text: str,
    translated_text: str,
) -> None:
    profile = _load_or_create_profile(project_dir, speaker_id)
    style_key, style_summary = _infer_style(source_text)

    evidence = list(profile.provenance.get("evidence_lines", []))
    if source_text not in evidence:
        evidence.append(source_text)

    profile.tone_spectrum["demo_style"] = style_summary
    profile.translation_notes["demo_style_rule"] = _style_translation_rule(style_key)
    profile.provenance = {
        **profile.provenance,
        "last_updated_page": page_id,
        "evidence_lines": evidence,
        "last_demo_translation": translated_text,
    }
    StateManager.upsert_character(project_dir, profile)


def _infer_style(source_text: str) -> tuple[str, str]:
    if "ございます" in source_text or "ください" in source_text:
        return "polite", "礼貌、克制、句尾偏正式"
    if "ぜ" in source_text or "知るか" in source_text or "しろ" in source_text:
        return "rough", "粗鲁、直接、句尾偏口语"
    return "neutral", "中性、平稳"


def _style_translation_rule(style_key: str) -> str:
    return {
        "polite": "中文译文使用礼貌克制表达，可使用“请”“您”等语气。",
        "rough": "中文译文使用直接口语表达，可使用“喂”“少废话”等语气。",
        "neutral": "中文译文保持自然中性。",
    }[style_key]


def _fake_translate(prompt: str) -> str:
    if "礼貌、克制" in prompt or "礼貌克制表达" in prompt:
        return "请您稍等一下。"
    if "粗鲁、直接" in prompt or "直接口语表达" in prompt:
        return "少废话，快点。"
    return "好的。"


def _snapshot_for(
    page_id: str,
    profile: CharacterState,
    traces: list[DemoBubbleTrace],
) -> CharacterMemorySnapshot:
    prompt_excerpt = ""
    for trace in reversed(traces):
        if trace.speaker_id == profile.character_id:
            prompt_excerpt = trace.prompt[:500]
            break

    return CharacterMemorySnapshot(
        page_id=page_id,
        speaker_id=profile.character_id,
        evidence_lines=tuple(profile.provenance.get("evidence_lines", [])),
        style_summary=profile.tone_spectrum.get("demo_style", ""),
        last_updated_page=str(profile.provenance.get("last_updated_page", "")),
        prompt_excerpt=prompt_excerpt,
    )
