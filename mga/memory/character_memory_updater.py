"""Page-sequential character memory updates for translated dialogue."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mga.memory.entities import CharacterState
from mga.memory.profile_loader import get_profile_as_dict
from mga.memory.speaker_filter import (
    build_token_index,
    find_canonical_match,
    is_generic_speaker,
    pick_canonical_id,
)
from mga.memory.state import StateManager

if TYPE_CHECKING:
    from mga.memory.service import MemoryService


@dataclass(frozen=True)
class CharacterMemoryUpdate:
    """Result of updating a character profile from one translated bubble."""

    memory_after: dict[str, Any]
    trace_item: dict[str, Any]


class CharacterMemoryUpdater:
    """Update structured character memory from page-sequential translations.

    Supports optional MemoryService for LRU-cached profile lookups.
    When memory_service is provided, profile lookups use O(1) L1 cache.
    """

    def __init__(
        self,
        project_dir: Path,
        memory_service: "MemoryService | None" = None,
    ) -> None:
        self.project_dir = project_dir
        self._memory_service = memory_service
        # Lazily-built token index for canonical matching.  Invalidated on
        # every upsert so newly-created characters are visible to subsequent
        # calls.
        self._token_index: dict[str, str] | None = None

    def _get_profile(self, speaker: str) -> CharacterState | None:
        """Get character profile via MemoryService cache or StateManager."""
        if self._memory_service is not None:
            profile = self._memory_service.get_character(speaker)
            if profile is not None:
                # Convert CharacterProfile back to CharacterState for compatibility
                return CharacterState(
                    character_id=profile.character_id,
                    name_jp=profile.name_jp,
                    name_zh=profile.name_zh,
                    archetype=profile.archetype,
                    speech_patterns=profile.speech_patterns,
                    catchphrases=profile.catchphrases,
                    tone_spectrum=profile.tone_spectrum,
                    translation_notes=profile.translation_notes,
                    relationship_speech=profile.relationships,
                    voice_evolutions=profile.voice_evolutions,
                    provenance=profile.provenance,
                )
        return StateManager.get_character(self.project_dir, speaker)

    def update_from_translation(
        self,
        *,
        speaker: str,
        bubble: object,
        page_id: str,
        translated_text: str,
        memory_before: dict[str, Any],
        prompt: str,
    ) -> CharacterMemoryUpdate:
        """Persist memory for one translated bubble and return audit data."""
        # Generic/trash speaker IDs (Narrator, Female character, Girl with hand
        # to mouth, …) must not pollute character memory.  This is the safety-net
        # gate; speaker_attribution_stage is the primary gate.
        # (docs/handoff-2026-06-22-memory-reassessment.md)
        if is_generic_speaker(speaker):
            return CharacterMemoryUpdate(
                memory_after={},
                trace_item={
                    "page_id": page_id,
                    "speaker_id": speaker,
                    "bubble_id": bubble.bubble_id,
                    "source_text": bubble.source_text,
                    "translated_text": translated_text,
                    "memory_before": memory_before,
                    "memory_after": {},
                    "prompt_excerpt": prompt[:500],
                    "skipped": "generic_speaker",
                },
            )
        memory_after = self._update_character_memory(
            speaker=speaker,
            bubble=bubble,
            page_id=page_id,
            translated_text=translated_text,
        )
        trace_item = {
            "page_id": page_id,
            "speaker_id": speaker,
            "bubble_id": bubble.bubble_id,
            "source_text": bubble.source_text,
            "translated_text": translated_text,
            "memory_before": memory_before,
            "memory_after": memory_after,
            "prompt_excerpt": prompt[:500],
        }
        return CharacterMemoryUpdate(memory_after=memory_after, trace_item=trace_item)

    def profile_for_speaker(self, speaker: str) -> dict[str, Any] | None:
        """Return a prompt-ready profile dict for a speaker, if persisted."""
        profile = self._get_profile(speaker)
        if profile is None:
            return None
        return get_profile_as_dict(profile)

    def profiles_for_page(self, page: object) -> dict[str, dict[str, Any]]:
        """Load prompt-ready profiles for all formal speakers on a page."""
        profiles: dict[str, dict[str, Any]] = {}
        for bubble in page.bubbles:
            speaker = bubble.speaker_id
            if not speaker or speaker in profiles:
                continue
            profile = self.profile_for_speaker(speaker)
            if profile is not None:
                profiles[speaker] = profile
        return profiles

    def _get_token_index(self) -> dict[str, str]:
        """Lazily build (and cache) the {token → character_id} lookup."""
        if self._token_index is None:
            characters = StateManager.list_characters(self.project_dir)
            self._token_index = build_token_index(characters)
        return self._token_index

    def _update_character_memory(
        self,
        *,
        speaker: str,
        bubble: object,
        page_id: str,
        translated_text: str,
    ) -> dict[str, Any]:
        profile = self._get_profile(speaker)

        if profile is None:
            # Safety-net canonicalisation: if speaker_attribution didn't run or
            # missed a variant, try to merge with an existing character via
            # name-token matching.  Without this, "Miko (美胡)" and "美胡" would
            # create separate entries when speaker_attribution is bypassed.
            canonical = find_canonical_match(speaker, self._get_token_index())
            if canonical and canonical != speaker:
                profile = self._get_profile(canonical)
                if profile is not None:
                    # Record the variant as an alias so future calls match faster
                    aliases = list(profile.provenance.get("aliases", []))
                    if speaker not in aliases:
                        aliases.append(speaker)
                    profile.provenance["aliases"] = aliases

        if profile is None:
            # Use a clean canonical ID (e.g. "美胡" instead of "miko(美胡)") so
            # that variant descriptions on later pages merge via token matching.
            clean_id = pick_canonical_id(speaker)
            profile = CharacterState(
                character_id=clean_id,
                name_jp=bubble.speaker_name or speaker,
            )

        style_key, style_summary = infer_speech_style(bubble.source_text)
        source_sample = (bubble.source_text or "").strip()
        translated_sample = (translated_text or "").strip()

        if style_summary:
            profile.tone_spectrum["observed_style"] = style_summary
            profile.translation_notes["style_rule"] = style_translation_rule(style_key)
        if getattr(bubble, "tone", None):
            profile.tone_spectrum["latest_tone"] = str(bubble.tone)
        if source_sample:
            profile.speech_patterns["latest_source_sample"] = source_sample

        evidence = list(profile.provenance.get("evidence_lines", []))
        if source_sample and source_sample not in evidence:
            evidence.append(source_sample)

        observations = list(profile.provenance.get("translation_observations", []))
        observations.append(
            {
                "page_id": page_id,
                "bubble_id": bubble.bubble_id,
                "source_text": source_sample,
                "translated_text": translated_sample,
            }
        )
        profile.provenance = {
            **profile.provenance,
            "last_updated_page": page_id,
            "evidence_lines": evidence,
            "translation_observations": observations[-20:],
        }

        StateManager.upsert_character(self.project_dir, profile)
        # Invalidate token index cache so newly-created characters are visible
        # to subsequent find_canonical_match calls.
        self._token_index = None
        return get_profile_as_dict(profile)


def infer_speech_style(source_text: str) -> tuple[str, str]:
    """Infer a coarse dialogue style from source text."""
    text = source_text or ""
    if "ございます" in text or "ください" in text or "です" in text or "ます" in text:
        return "polite", "礼貌、克制、句尾偏正式"
    if "ぜ" in text or "知るか" in text or "しろ" in text or "だろ" in text:
        return "rough", "粗鲁、直接、句尾偏口语"
    return "neutral", "中性、平稳"


def style_translation_rule(style_key: str) -> str:
    """Return the prompt-facing translation rule for an inferred style."""
    return {
        "polite": "中文译文使用礼貌克制表达，可使用“请”“您”等语气。",
        "rough": "中文译文使用直接口语表达，可使用“喂”“少废话”等语气。",
        "neutral": "中文译文保持自然中性。",
    }[style_key]
