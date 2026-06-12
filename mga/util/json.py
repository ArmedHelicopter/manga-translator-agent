"""JSON parsing helpers for LLM responses."""

from __future__ import annotations

import json


def parse_json_from_llm_response(text: str) -> dict:
    """Parse JSON from a raw LLM response.

    The parser accepts direct JSON, markdown fenced JSON, and responses with
    commentary before/after the JSON payload. It raises ``json.JSONDecodeError``
    when no valid JSON object or array can be recovered.
    """
    raw = text or ""
    if not raw.strip():
        raise json.JSONDecodeError(
            "Cannot parse JSON from empty LLM response",
            doc="",
            pos=0,
        )

    try:
        return json.loads(raw)
    except json.JSONDecodeError as direct_exc:
        stripped = raw.strip()

        candidates: list[str] = []
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines and lines[0].strip().startswith("```"):
                if len(lines) >= 2 and lines[-1].strip() == "```":
                    candidates.append("\n".join(lines[1:-1]).strip())
                else:
                    candidates.append("\n".join(lines[1:]).strip())

        candidates.append(stripped)

        for candidate in list(candidates):
            obj_start = candidate.find("{")
            obj_end = candidate.rfind("}")
            if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
                candidates.append(candidate[obj_start : obj_end + 1].strip())

            arr_start = candidate.find("[")
            arr_end = candidate.rfind("]")
            if arr_start != -1 and arr_end != -1 and arr_end > arr_start:
                candidates.append(candidate[arr_start : arr_end + 1].strip())

        seen: set[str] = set()
        for candidate in candidates:
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue

        raise direct_exc
