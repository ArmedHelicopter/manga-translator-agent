"""Shared image helpers for OpenAI-compatible vision providers."""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import Any


DEFAULT_MAX_IMAGE_DIMENSION = 2048
DEFAULT_JPEG_QUALITY = 85


def read_image_bytes(path: str | Path) -> bytes:
    """Read image bytes from disk and fail with a clear missing-file message."""
    image_path = Path(path)
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {path}")
    return image_path.read_bytes()


def _resize_image_if_needed(image_bytes: bytes, max_dimension: int = DEFAULT_MAX_IMAGE_DIMENSION) -> bytes:
    """Downscale image bytes while preserving aspect ratio."""
    from PIL import Image

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            width, height = img.size
            if max(width, height) <= max_dimension:
                return image_bytes

            resized = img.copy()
            resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
            resized.thumbnail((max_dimension, max_dimension), resampling)

            buf = io.BytesIO()
            resized.save(buf, format="PNG", optimize=True)
            return buf.getvalue()
    except Exception:
        return image_bytes


def _encode_vision_image(image_bytes: bytes, jpeg_quality: int = DEFAULT_JPEG_QUALITY) -> tuple[str, bytes]:
    """Encode a PIL-readable image as compact JPEG for vision APIs."""
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode in {"RGBA", "LA"} or (img.mode == "P" and "transparency" in img.info):
                rgba = img.convert("RGBA")
                rgb = Image.new("RGB", rgba.size, (255, 255, 255))
                rgb.paste(rgba, mask=rgba.getchannel("A"))
            else:
                rgb = img.convert("RGB")

            buf = io.BytesIO()
            rgb.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
            return "image/jpeg", buf.getvalue()
    except Exception:
        return "image/png", image_bytes


def make_image_parts_base64(images: list[bytes]) -> list[dict[str, Any]]:
    """Build OpenAI-compatible base64 image parts with bounded payload size."""
    parts: list[dict[str, Any]] = []
    for image in images:
        resized = _resize_image_if_needed(image)
        mime_type, encoded_image = _encode_vision_image(resized)
        parts.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{base64.standard_b64encode(encoded_image).decode('ascii')}",
                },
            }
        )
    return parts


def inject_images_into_messages(
    messages: list[dict[str, Any]],
    image_parts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Attach image parts to the last user message without mutating callers' message dicts."""
    result = [dict(message) for message in messages]
    if result and result[-1].get("role") == "user":
        existing = result[-1].get("content", "")
        if isinstance(existing, str):
            result[-1]["content"] = [{"type": "text", "text": existing}, *image_parts]
        elif isinstance(existing, list):
            result[-1]["content"] = [*existing, *image_parts]
    return result
