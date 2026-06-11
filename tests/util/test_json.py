"""Tests for LLM JSON response parsing."""

from __future__ import annotations

import json

import pytest

from mga.util import parse_json_from_llm_response


def test_parse_direct_json_object() -> None:
    assert parse_json_from_llm_response('{"ok": true, "count": 2}') == {
        "ok": True,
        "count": 2,
    }


def test_parse_fenced_json_object() -> None:
    response = """```json
{"translations": [{"text": "你好"}]}
```"""

    assert parse_json_from_llm_response(response) == {"translations": [{"text": "你好"}]}


def test_parse_json_object_embedded_in_commentary() -> None:
    response = "Here is the result:\n{\"bubble_id\": \"b1\", \"text\": \"早上好\"}\nDone."

    assert parse_json_from_llm_response(response) == {"bubble_id": "b1", "text": "早上好"}


def test_parse_json_array_embedded_in_commentary() -> None:
    response = "Result:\n[{\"bubble_id\": \"b1\"}, {\"bubble_id\": \"b2\"}]"

    assert parse_json_from_llm_response(response) == [
        {"bubble_id": "b1"},
        {"bubble_id": "b2"},
    ]


def test_parse_empty_response_raises_decode_error() -> None:
    with pytest.raises(json.JSONDecodeError, match="empty LLM response"):
        parse_json_from_llm_response("  \n")


def test_parse_invalid_response_raises_decode_error() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_json_from_llm_response("not json")
