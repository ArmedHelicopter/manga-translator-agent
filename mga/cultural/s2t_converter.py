"""Simplified/Traditional Chinese conversion via opencc, with graceful degradation.

When opencc is not installed, the converter is a no-op (returns text unchanged).
This ensures the pipeline never crashes when opencc is unavailable.

Supported variants:
    auto    — no conversion (default)
    s2t     — simplified → traditional (opencc s2t.json)
    t2s     — traditional → simplified (opencc t2s.json)
    tw      — simplified → Taiwan traditional (opencc s2tw.json)
    hk      — simplified → Hong Kong traditional (opencc s2hk.json)
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# opencc config names for each variant
_CONVERSIONS = {
    "s2t": "s2t",   # 简体→繁体
    "t2s": "t2s",   # 繁体→简体
    "tw": "s2tw",   # 简体→台湾正体
    "hk": "s2hk",   # 简体→香港繁体
}


class S2TConverter:
    """Simplified/Traditional Chinese converter with graceful degradation.

    Args:
        variant: Conversion variant. One of: auto, s2t, t2s, tw, hk.
            "auto" or empty/None disables conversion (no-op).

    Usage:
        converter = S2TConverter("s2t")
        converted = converter.convert("测试")  # "測試" if opencc available, else "测试"
    """

    def __init__(self, variant: str = "auto") -> None:
        self._variant = variant or "auto"
        self._converter = None
        self._available = False
        self._init_converter()

    def _init_converter(self) -> None:
        """Initialize the opencc converter if available."""
        if self._variant in ("auto", "", None):
            return

        if self._variant not in _CONVERSIONS:
            logger.warning(
                "Unknown chinese_variant %r; S2T conversion disabled (no-op)",
                self._variant,
            )
            return

        try:
            import opencc

            config_name = _CONVERSIONS[self._variant]
            self._converter = opencc.OpenCC(config_name)
            self._available = True
            logger.debug("opencc converter initialized for variant %r", self._variant)
        except ImportError:
            logger.warning(
                "opencc not installed; chinese_variant=%s will be a no-op. "
                "Install with: pip install opencc",
                self._variant,
            )
        except Exception as exc:
            logger.warning(
                "opencc conversion init failed for variant %r (%s); disabled (no-op)",
                self._variant,
                exc,
            )

    @property
    def available(self) -> bool:
        """True if the converter is available and active."""
        return self._available

    @property
    def variant(self) -> str:
        """The configured variant."""
        return self._variant

    def convert(self, text: str) -> str:
        """Convert text to the target variant.

        Returns the original text unchanged if:
        - variant is "auto"
        - opencc is not installed
        - converter initialization failed
        - text is empty/None
        """
        if not text or not self._converter:
            return text
        try:
            return self._converter.convert(text)
        except Exception as exc:
            logger.warning(
                "S2T conversion failed for variant %r (%s); returning original text",
                self._variant,
                exc,
            )
            return text
