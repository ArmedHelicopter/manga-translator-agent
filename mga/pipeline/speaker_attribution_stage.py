"""Conservative formal speaker attribution from Vision hints."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from mga.memory.entities import CharacterState
from mga.memory.state import StateManager
from mga.models import ProjectConfig

from .stages import PipelineContext, PipelineStage


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
        candidates = self._load_candidates(project_dir)
        trace: list[dict] = []

        for page in context.pages:
            page_assignments: dict[str, str] = {}
            for bubble in page.bubbles:
                item = self._attribute_bubble(bubble, candidates, page_assignments, project_dir)
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
    ) -> dict:
        if getattr(bubble, "speaker_id", None):
            return self._trace_item(
                bubble=bubble,
                assigned_speaker_id=bubble.speaker_id,
                confidence=1.0,
                accepted=True,
                reason="existing speaker_id preserved",
            )

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

        if self._is_generic_hint(normalized_hint):
            return self._trace_item(
                bubble=bubble,
                assigned_speaker_id=page_assignments.get(normalized_hint),
                confidence=0.35 if normalized_hint in page_assignments else 0.1,
                accepted=False,
                reason="generic provisional speaker is not formal attribution",
            )

        if normalized_hint in page_assignments:
            return self._trace_item(
                bubble=bubble,
                assigned_speaker_id=page_assignments[normalized_hint],
                confidence=0.9,
                accepted=True,
                reason="same-page speaker hint already matched a known character",
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
            new_id = self._create_candidate_character(project_dir, hint)
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

    def _create_candidate_character(self, project_dir: Path, hint: str) -> str:
        """Cold-start: register a candidate character from a non-generic speaker hint.

        Idempotent — a later bubble/page with the same hint reuses the existing id
        instead of creating a duplicate.
        """
        character_id = self._normalize_label(hint)
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
        return character_id

    def _load_candidates(self, project_dir: Path) -> list[_SpeakerCandidate]:
        candidates: list[_SpeakerCandidate] = []
        for character in StateManager.list_characters(project_dir):
            labels = set(self._labels_for_character(character))
            if labels:
                candidates.append(
                    _SpeakerCandidate(character_id=character.character_id, labels=labels)
                )
        return candidates

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
        return bool(_GENERIC_SPEAKER_RE.match(normalized_hint))
