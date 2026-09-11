"""Vision capability probing for stage providers.

Used by the CLI pre-check to fail fast (or auto-switch, when explicitly
requested) when the configured vision-stage model rejects image input —
e.g. a text-only model selected on a multimodal provider.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 1x1 px PNG used as the cheapest possible image-input probe.
TINY_PNG: bytes = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

_PROBE_PROMPT = "Reply with OK."
PROBE_TIMEOUT_SECONDS = 20

# Error fragments that indicate "this model does not take images" as opposed
# to connectivity/auth problems.
_IMAGE_REJECTION_PATTERNS = (
    "image input",  # MiMo: "No endpoints found that support image input"
    "does not support image",
    "image_url is not supported",
    "does not support vision",
    "vision is not supported",
    "multimodal",
    "invalid content type: image",
)

# Model-name fragments that are clearly not chat/vision models; skipped
# during sibling-model discovery.
_NON_CHAT_MODEL_HINTS = (
    "tts",
    "asr",
    "embed",
    "whisper",
    "audio",
    "rerank",
    "voiceclone",
    "voicedesign",
)

_SUPPORTS_VISION_FALSE = "provider reports supports_vision=False"


def is_image_rejection_error(error: BaseException | str) -> bool:
    """Return True when *error* looks like an image-input rejection."""
    message = str(error).lower()
    if message == _SUPPORTS_VISION_FALSE.lower():
        return True
    return any(pattern in message for pattern in _IMAGE_REJECTION_PATTERNS)


def probe_vision(provider: Any) -> tuple[bool, str]:
    """Send a 1px image to *provider*; return (capable, error_message)."""
    if getattr(provider, "supports_vision", True) is False:
        return False, _SUPPORTS_VISION_FALSE
    try:
        provider.vision(
            messages=[{"role": "user", "content": _PROBE_PROMPT}],
            images=[TINY_PNG],
            timeout=PROBE_TIMEOUT_SECONDS,
        )
        return True, ""
    except Exception as exc:  # noqa: BLE001 - probe converts any failure to a result.
        return False, str(exc)


def list_models(provider: Any) -> list[str]:
    """Best-effort model listing for OpenAI-compatible providers."""
    client = getattr(provider, "_client", None)
    models = getattr(client, "models", None)
    if models is None or not hasattr(models, "list"):
        return []
    try:
        return [getattr(m, "id", "") for m in models.list() if getattr(m, "id", "")]
    except Exception as exc:  # noqa: BLE001 - discovery is best-effort.
        logger.debug("Model listing failed: %s", exc)
        return []


def _common_prefix_len(a: str, b: str) -> int:
    n = 0
    for ca, cb in zip(a, b):
        if ca != cb:
            break
        n += 1
    return n


def discover_vision_models(
    provider_name: str,
    settings: dict | None,
    *,
    current_model: str = "",
    max_probes: int = 8,
) -> list[str]:
    """Probe sibling models on the same provider/key for image-input support.

    Returns vision-capable model names ordered by similarity to
    *current_model* (longest shared prefix first).
    """
    from .registry import get_provider

    try:
        base_provider = get_provider(provider_name, **dict(settings or {}))
    except Exception as exc:  # noqa: BLE001 - discovery is best-effort.
        logger.debug("Could not instantiate provider %r for discovery: %s", provider_name, exc)
        return []

    names = list_models(base_provider)
    candidates = [
        name
        for name in names
        if name != current_model
        and not any(hint in name.lower() for hint in _NON_CHAT_MODEL_HINTS)
    ]
    candidates.sort(key=lambda name: _common_prefix_len(name, current_model), reverse=True)

    capable: list[str] = []
    for name in candidates[:max_probes]:
        probe_settings = dict(settings or {})
        probe_settings["vision_model"] = name
        probe_settings.pop("model", None)
        try:
            candidate_provider = get_provider(provider_name, **probe_settings)
        except Exception:  # noqa: BLE001
            continue
        ok, _err = probe_vision(candidate_provider)
        if ok:
            capable.append(name)
    return capable
