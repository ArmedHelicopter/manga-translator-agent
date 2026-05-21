"""Honorific compensation system -- 4 dimensions per SPEC Section 8."""

from __future__ import annotations

import re
from enum import Enum


class HonorificLevel(Enum):
    """Formality tiers in Japanese speech."""
    SONKEIGO = "sonkeigo"      # 尊敬語 -- respectful (upward)
    KENJOUGO = "kenjougo"      # 謙譲語 -- humble (inward)
    TEINEIGO = "teineigo"      # 丁寧語 -- polite (neutral)
    TAMEGUCHI = "tameguchi"    # ため口 -- casual (intimate)
    DANNAI = "dannai"          # 段内   -- intra-group (in-group)


_STATUS_RANKS: dict[str, int] = {"junior": 0, "peer": 1, "senior": 2, "authority": 3}

_ADDRESS_TEMPLATES: dict[tuple[HonorificLevel, str], str] = {
    (HonorificLevel.SONKEIGO, "zh-CN"): "您",
    (HonorificLevel.SONKEIGO, "en"): "you (respectful)",
    (HonorificLevel.KENJOUGO, "zh-CN"): "在下/鄙人",
    (HonorificLevel.KENJOUGO, "en"): "I (humble)",
    (HonorificLevel.TEINEIGO, "zh-CN"): "您/你",
    (HonorificLevel.TEINEIGO, "en"): "you",
    (HonorificLevel.TAMEGUCHI, "zh-CN"): "你",
    (HonorificLevel.TAMEGUCHI, "en"): "you",
    (HonorificLevel.DANNAI, "zh-CN"): "你/咱们",
    (HonorificLevel.DANNAI, "en"): "we/you",
}

_ZH_YOU_RE = re.compile(r"^(你|您|妳)")
_EN_YOU_RE = re.compile(r"^(you|You)\b")


class HonorificCompensator:
    """Analyses and compensates Japanese honorific levels for translation.

    Implements the four-dimension model from SPEC Section 8:
    speaker status, listener status, in-group/out-group membership,
    and relationship distance.
    """

    def analyze(
        self,
        speaker_profile: dict,
        listener_profile: dict,
        relationship: dict,
    ) -> HonorificLevel:
        """Determine the honorific level from speaker/listener profiles."""
        s_rank = _STATUS_RANKS.get(speaker_profile.get("status", "peer"), 1)
        l_rank = _STATUS_RANKS.get(listener_profile.get("status", "peer"), 1)
        s_in = speaker_profile.get("in_group", True)
        l_in = listener_profile.get("in_group", True)
        distance = relationship.get("distance", "neutral")
        familiarity = relationship.get("familiarity", "acquaintance")

        # In-group casual override
        if s_in and l_in and familiarity in ("close", "intimate"):
            return HonorificLevel.DANNAI

        # Listener is senior / higher status -> respectful
        if l_rank > s_rank:
            return HonorificLevel.SONKEIGO if distance == "formal" else HonorificLevel.TEINEIGO

        # Speaker is senior but listener is out-group -> polite
        if s_rank > l_rank and not l_in:
            return HonorificLevel.TEINEIGO

        # Casual peers
        if familiarity in ("close", "intimate") and distance != "formal":
            return HonorificLevel.TAMEGUCHI

        return HonorificLevel.TEINEIGO

    def compensate(self, source_text: str, level: HonorificLevel, target_lang: str) -> str:
        """Adjust target-language text to reflect the detected honorific level."""
        address = _ADDRESS_TEMPLATES.get((level, target_lang), "")
        if not address:
            return source_text

        # Swap second-person pronoun at sentence start for the appropriate form
        pattern = _ZH_YOU_RE if target_lang == "zh-CN" else _EN_YOU_RE if target_lang == "en" else None
        if pattern is not None:
            match = pattern.match(source_text)
            if match:
                return address + source_text[match.end():]
        return source_text

    def get_form_of_address(self, character_name: str, target: str, relationship: dict) -> str:
        """Return the appropriate form of address for *character_name*."""
        familiarity = relationship.get("familiarity", "acquaintance")
        if target == "zh-CN" and familiarity == "peer":
            return f"{character_name}同学"
        return character_name
