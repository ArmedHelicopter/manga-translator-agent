"""Conservative formal speaker attribution from Vision hints."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from mga.memory.entities import CharacterState
from mga.memory.speaker_filter import (
    build_token_index,
    extract_name_tokens,
    find_canonical_match,
    is_generic_speaker,
    pick_canonical_id,
)
from mga.memory.state import StateManager
from mga.models import ProjectConfig

from .stages import PipelineContext, PipelineStage

# Retained for backward compatibility with any external callers that import it.
# New code should use mga.memory.speaker_filter.is_generic_speaker instead.
_GENERIC_SPEAKER_RE = re.compile(
    r"^(unknown|unidentified|someone|person|speaker|girl|boy|man|woman|"
    r"unknown[-_ ].+|.+[-_ ]near[-_ ].+|.+[-_ ]left|.+[-_ ]right)$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class _SpeakerCandidate:
    character_id: str
    labels: set[str]


class SpeakerAttributionStage(PipelineStage):
    """Promote high-confidence speaker hints into formal speaker_id values."""

    @property
    def name(self) -> str:
        return "speaker_attribution"

    @property
    def order(self) -> int:
        return 28

    def execute(self, context: PipelineContext) -> PipelineContext:
        cfg: ProjectConfig = context.project_config
        project_dir = Path(cfg.working_dir) if cfg.working_dir else Path(".")
        characters = StateManager.list_characters(project_dir)
        candidates = self._build_candidates(characters)
        # Token index enables matching variant descriptions ("Miko (美胡)",
        # "miko_美胡_the_girl_with_long_hair") to the same character via shared
        # name tokens (e.g. "美胡").  Without it, each variant creates a separate
        # character entry (docs/handoff-2026-06-22-memory-reassessment.md).
        token_index = build_token_index(characters)
        trace: list[dict] = []

        for page in context.pages:
            page_assignments: dict[str, str] = {}
            for bubble in page.bubbles:
                item = self._attribute_bubble(
                    bubble, candidates, page_assignments, project_dir, token_index
                )
                item["page_id"] = page.page_id
                item["bubble_id"] = bubble.bubble_id
                trace.append(item)
                if item["accepted"] and item["assigned_speaker_id"]:
                    bubble.speaker_id = item["assigned_speaker_id"]
                    label = self._hint_for_bubble(bubble)
                    if label:
                        page_assignments[self._normalize_label(label)] = bubble.speaker_id

        context.artifacts[self.name] = {
            "pages_processed": len(context.pages),
            "trace": trace,
            "accepted": sum(1 for item in trace if item["accepted"]),
        }
        return context

    def _attribute_bubble(
        self,
        bubble: object,
        candidates: list[_SpeakerCandidate],
        page_assignments: dict[str, str],
        project_dir: Path,
        token_index: dict[str, str],
    ) -> dict:
        existing_speaker_id = getattr(bubble, "speaker_id", None)

        # ── Canonicalise vision-set speaker_id ──
        # Vision emits raw descriptions as speaker_id ("Girl with dark hair (Miho)",
        # "Female character", "Narrator", …).  Without canonicalisation these become
        # 80+ fragmented character entries.  Two sub-steps:
        #   1. Clear generic IDs so the hint-based flow gets a chance.
        #   2. Merge variant IDs to a canonical form via name-token matching.
        # (docs/handoff-2026-06-22-memory-reassessment.md)
        if existing_speaker_id:
            if is_generic_speaker(existing_speaker_id):
                # Generic vision-set IDs (Narrator, Female character, …) must not
                # become character entries.  Clear and fall through to hint-based flow.
                existing_speaker_id = None
                bubble.speaker_id = None
            else:
                canonical = find_canonical_match(existing_speaker_id, token_index)
                if canonical and canonical != existing_speaker_id:
                    bubble.speaker_id = canonical
                    return self._trace_item(
                        bubble=bubble,
                        assigned_speaker_id=canonical,
                        confidence=0.95,
                        accepted=True,
                        reason="vision speaker_id canonicalised to existing character",
                    )
                # Try cleaning the ID (e.g. "Miko (美胡)" → "美胡")
                clean = pick_canonical_id(existing_speaker_id)
                if clean and clean != self._normalize_label(existing_speaker_id):
                    existing_character = StateManager.get_character(project_dir, clean)
                    if existing_character:
                        bubble.speaker_id = existing_character.character_id
                        return self._trace_item(
                            bubble=bubble,
                            assigned_speaker_id=existing_character.character_id,
                            confidence=0.95,
                            accepted=True,
                            reason="vision speaker_id cleaned to existing character",
                        )
                    bubble.speaker_id = clean
                    return self._trace_item(
                        bubble=bubble,
                        assigned_speaker_id=clean,
                        confidence=0.9,
                        accepted=True,
                        reason="vision speaker_id canonicalised to clean id",
                    )
                # No canonicalisation needed — preserve as-is
                return self._trace_item(
                    bubble=bubble,
                    assigned_speaker_id=existing_speaker_id,
                    confidence=1.0,
                    accepted=True,
                    reason="existing speaker_id preserved",
                )

        # ── Hint-based attribution (no pre-existing speaker_id) ──
        hint = self._hint_for_bubble(bubble)
        normalized_hint = self._normalize_label(hint)
        if not normalized_hint:
            return self._trace_item(
                bubble=bubble,
                assigned_speaker_id=None,
                confidence=0.0,
                accepted=False,
                reason="no speaker hint",
            )

        if is_generic_speaker(hint):
            return self._trace_item(
                bubble=bubble,
                assigned_speaker_id=page_assignments.get(normalized_hint),
                confidence=0.35 if normalized_hint in page_assignments else 0.1,
                accepted=False,
                reason="generic provisional speaker is not formal attribution",
            )

        # Same-page dedup: identical hint already attributed on this page.
        if normalized_hint in page_assignments:
            return self._trace_item(
                bubble=bubble,
                assigned_speaker_id=page_assignments[normalized_hint],
                confidence=0.9,
                accepted=True,
                reason="same-page speaker hint already matched a known character",
            )

        # Token-based matching: "Miko (美胡)" matches existing "美胡" via shared
        # CJK token, preventing fragmentation across pages.
        canonical = find_canonical_match(hint, token_index)
        if canonical:
            page_assignments[normalized_hint] = canonical
            return self._trace_item(
                bubble=bubble,
                assigned_speaker_id=canonical,
                confidence=0.95,
                accepted=True,
                reason="speaker hint matched existing character via name token",
            )

        for candidate in candidates:
            if normalized_hint in candidate.labels:
                return self._trace_item(
                    bubble=bubble,
                    assigned_speaker_id=candidate.character_id,
                    confidence=0.95,
                    accepted=True,
                    reason="speaker hint exactly matches existing character profile",
                )

        # Cold-start creation: a non-generic hint with no known match registers a candidate
        # character so translation/QA/memory have an anchor. Without this, a fresh work
        # (empty memory) never assigns any speaker_id, leaving memory/character profiles
        # empty for the entire run (docs/handoff-2026-06-19-pipeline-run.md).
        if len(normalized_hint) >= 2:
            new_id = self._create_candidate_character(project_dir, hint, token_index)
            page_assignments[normalized_hint] = new_id
            return self._trace_item(
                bubble=bubble,
                assigned_speaker_id=new_id,
                confidence=0.6,
                accepted=True,
                reason="cold-start: created new character from non-generic speaker hint",
            )

        return self._trace_item(
            bubble=bubble,
            assigned_speaker_id=None,
            confidence=0.2,
            accepted=False,
            reason="speaker hint did not match existing character profile",
        )

    def _create_candidate_character(
        self, project_dir: Path, hint: str, token_index: dict[str, str]
    ) -> str:
        """Cold-start: register a candidate character from a non-generic speaker hint.

        Uses pick_canonical_id to choose a clean character_id (e.g. "美胡" instead
        of "miko(美胡)") so that variant descriptions on later pages merge via
        token matching instead of fragmenting into separate entries.

        Idempotent — a later bubble/page with the same hint reuses the existing id
        instead of creating a duplicate.
        """
        character_id = pick_canonical_id(hint)
        existing = StateManager.get_character(project_dir, character_id)
        if existing is not None:
            return existing.character_id
        StateManager.upsert_character(
            project_dir,
            CharacterState(
                character_id=character_id,
                name_jp=hint,
                name_zh=hint,
                provenance={"source": "cold_start_speaker_hint"},
            ),
        )
        # Register the new character's tokens so subsequent bubbles on later
        # pages match it via find_canonical_match (e.g. "Miko (美胡)" → "美胡").
        for token in extract_name_tokens(hint):
            if token not in token_index:
                token_index[token] = character_id
        return character_id

    def _build_candidates(
        self, characters: list[CharacterState]
    ) -> list[_SpeakerCandidate]:
        candidates: list[_SpeakerCandidate] = []
        for character in characters:
            labels = set(self._labels_for_character(character))
            if labels:
                candidates.append(
                    _SpeakerCandidate(character_id=character.character_id, labels=labels)
                )
        return candidates

    def _load_candidates(self, project_dir: Path) -> list[_SpeakerCandidate]:
        """Backward-compatible wrapper. Prefer _build_candidates to avoid
        a second StateManager.list_characters call."""
        return self._build_candidates(StateManager.list_characters(project_dir))

    def _labels_for_character(self, character: CharacterState) -> Iterable[str]:
        for label in (
            character.character_id,
            character.name_jp,
            character.name_zh,
        ):
            normalized = self._normalize_label(label)
            if normalized:
                yield normalized
        aliases = character.provenance.get("aliases", [])
        if isinstance(aliases, list):
            for alias in aliases:
                normalized = self._normalize_label(str(alias))
                if normalized:
                    yield normalized

    def _hint_for_bubble(self, bubble: object) -> str:
        return (
            getattr(bubble, "provisional_speaker", None)
            or getattr(bubble, "speaker_name", None)
            or ""
        )

    def _trace_item(
        self,
        *,
        bubble: object,
        assigned_speaker_id: str | None,
        confidence: float,
        accepted: bool,
        reason: str,
    ) -> dict:
        return {
            "provisional_speaker": getattr(bubble, "provisional_speaker", None),
            "speaker_name": getattr(bubble, "speaker_name", None),
            "assigned_speaker_id": assigned_speaker_id,
            "confidence": confidence,
            "accepted": accepted,
            "reason": reason,
        }

    @staticmethod
    def _normalize_label(label: str | None) -> str:
        if not label:
            return ""
        return re.sub(r"\s+", "", str(label).strip().casefold())

    @staticmethod
    def _is_generic_hint(normalized_hint: str) -> bool:
        """Backward-compatible wrapper. Prefer is_generic_speaker from speaker_filter."""
        return is_generic_speaker(normalized_hint)
