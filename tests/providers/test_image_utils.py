"""Tests for shared provider image helpers."""

from __future__ import annotations

import base64
import io
import re

import pytest
from PIL import Image

from mga.providers._image_utils import (
    _resize_image_if_needed,
    inject_images_into_messages,
    make_image_parts_base64,
    read_image_bytes,
)


def test_read_image_bytes_returns_file_contents(tmp_path) -> None:
    image = tmp_path / "page.png"
    image.write_bytes(b"image-bytes")

    assert read_image_bytes(image) == b"image-bytes"


def test_read_image_bytes_missing_file_has_clear_message(tmp_path) -> None:
    missing = tmp_path / "missing.png"

    with pytest.raises(FileNotFoundError, match=re.escape(f"Image not found: {missing}")):
        read_image_bytes(missing)


def test_make_image_parts_base64_builds_openai_image_parts() -> None:
    parts = make_image_parts_base64([b"first", b"second"])

    assert parts == [
        {
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64," + base64.standard_b64encode(b"first").decode("ascii"),
            },
        },
        {
            "type": "image_url",
            "image_url": {
                "url": "data:image/png;base64," + base64.standard_b64encode(b"second").decode("ascii"),
            },
        },
    ]


def _make_png_bytes(size: tuple[int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="PNG")
    return buf.getvalue()


def test_resize_image_if_needed_keeps_small_image_unchanged() -> None:
    image_bytes = _make_png_bytes((320, 200))

    assert _resize_image_if_needed(image_bytes) == image_bytes


def test_resize_image_if_needed_caps_largest_dimension() -> None:
    image_bytes = _make_png_bytes((3000, 1500))

    resized = _resize_image_if_needed(image_bytes)

    with Image.open(io.BytesIO(resized)) as image:
        assert image.size == (2048, 1024)


def test_make_image_parts_base64_resizes_and_encodes_large_images_as_jpeg() -> None:
    image_bytes = _make_png_bytes((3000, 1500))

    part = make_image_parts_base64([image_bytes])[0]
    url = part["image_url"]["url"]

    assert url.startswith("data:image/jpeg;base64,")
    encoded = url.removeprefix("data:image/jpeg;base64,")
    with Image.open(io.BytesIO(base64.standard_b64decode(encoded))) as image:
        assert image.format == "JPEG"
        assert image.size == (2048, 1024)


def test_inject_images_into_string_user_message_without_mutating_input() -> None:
    image_parts = make_image_parts_base64([b"image"])
    messages = [{"role": "user", "content": "Please inspect this page."}]

    result = inject_images_into_messages(messages, image_parts)

    assert messages == [{"role": "user", "content": "Please inspect this page."}]
    assert result == [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Please inspect this page."},
                image_parts[0],
            ],
        }
    ]


def test_inject_images_into_list_user_message_without_mutating_input() -> None:
    text_part = {"type": "text", "text": "Inspect."}
    image_parts = make_image_parts_base64([b"image"])
    messages = [{"role": "user", "content": [text_part]}]

    result = inject_images_into_messages(messages, image_parts)

    assert messages == [{"role": "user", "content": [text_part]}]
    assert result[0]["content"] == [text_part, image_parts[0]]
    assert result[0]["content"] is not messages[0]["content"]


def test_inject_images_leaves_non_user_tail_unchanged() -> None:
    messages = [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
    ]

    result = inject_images_into_messages(messages, make_image_parts_base64([b"image"]))

    assert result == messages
    assert result is not messages
