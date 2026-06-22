"""Parsing utilities for LLM responses - extracted from translation_stage."""

from __future__ import annotations

import json
import re
from typing import Any

from mga.models.translation import (
    FootnoteEntry,
    PersonaRenderTrace,
    SemanticTranslation,
    TranslationCandidate,
)


def parse_jsonish_response(raw: str) -> tuple[str, dict | None]:
    """Parse LLM response - handles both plain text and JSON formats."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()

    parsed = None
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
    else:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
            except ValueError:
                parsed = None
    return text, parsed if isinstance(parsed, dict) else None


_LEADING_BOLD_LABEL_RE = re.compile(r"^\s*\*\*[^*\n：:]{1,40}[:：]\*\*[\s]*")
_LEADING_PLAIN_LABEL_RE = re.compile(
    r"^\s*(?:Translation|Corrected\s+Translation|Final\s+Translation|"
    r"译文|修正翻译|最终译文|最终翻译|翻译)\s*[:：]\s*",
    re.IGNORECASE,
)


def clean_translation_text(text: str) -> str:
    """Strip LLM chatter / markdown labels that leak into translation output.

    Manga dialogue never opens with a bold markdown label or a 'Translation:'
    header, so stripping these leading markers is safe. Applied at every point
    translation text is stored or written (qa re-translate, output writer,
    render) so neither the rendered image nor the translation JSON contains
    markdown like '**Corrected Translation:**'. Conservative: only removes
    unambiguous chatter markers (markdown labels, code fences, wrapping bold);
    never strips dialogue content.
    """
    s = (text or "").strip()
    if not s:
        return s
    # Strip a leading code fence wrapping the whole response.
    if s.startswith("```"):
        lines = s.splitlines()
        if len(lines) >= 3 and lines[-1].strip().startswith("```"):
            s = "\n".join(lines[1:-1]).strip()
    # Leading markdown bold label, e.g. '**Corrected Translation:**'.
    s = _LEADING_BOLD_LABEL_RE.sub("", s).strip()
    # Leading plain label followed by a colon.
    s = _LEADING_PLAIN_LABEL_RE.sub("", s).strip()
    # Whole-string markdown bold wrapping the translation, e.g. '**第35话**'.
    if s.startswith("**") and s.endswith("**") and s.count("**") == 2:
        s = s[2:-2].strip()
    return s


JP_HONORIFIC_PATTERN = re.compile(r"([ぁ-ゖァ-ヺー・]{1,12})(?:ちゃん|さん|くん|君|様)")
ZH_NAME_SUFFIX_PATTERN = re.compile(r"([一-鿿]{1,6})(?:酱|醬)")
RATIONALE_TERM_RE = re.compile(r"[「『\"]([^「」『』\"]{1,20})[」』\"]")
KATAKANA_RE = re.compile(r"[ァ-ヺー]{2,}")
TEXT_FIELD_RE = re.compile(r'"text"\s*:\s*"((?:\\.|[^"\\])*)"', flags=re.DOTALL)
FOOTNOTE_ITEM_RE = re.compile(
    r'"original"\s*:\s*"((?:\\.|[^"\\])*)"\s*,\s*'
    r'"translation"\s*:\s*"((?:\\.|[^"\\])*)"\s*,\s*'
    r'"type"\s*:\s*"(loanword|sfx|name)"',
    flags=re.DOTALL,
)


def parse_translation_response(bubble_id: str, raw: str) -> TranslationCandidate:
    """Parse LLM response - handles both plain text and JSON formats."""
    text, parsed = parse_jsonish_response(raw)

    if isinstance(parsed, dict):
        footnotes = []
        for fn in parsed.get("footnotes", []):
            if isinstance(fn, dict):
                footnotes.append(FootnoteEntry(**fn))
        # Accept all footnote types: loanword, sfx, coined, cultural, fictional
        footnotes = [
            fn for fn in footnotes
            if fn.type in {"loanword", "sfx", "coined", "cultural", "fictional"}
        ]
        footnotes = augment_footnotes_from_rationale(
            text=parsed.get("text", parsed.get("translation", text)),
            rationale=parsed.get("rationale", ""),
            footnotes=footnotes,
        )
        return TranslationCandidate(
            bubble_id=bubble_id,
            text=parsed.get("text", parsed.get("translation", text)),
            rationale=parsed.get("rationale", ""),
            confidence=float(parsed.get("confidence", 0.8)),
            footnotes=footnotes,
        )

    fallback_text, fallback_footnotes = extract_structured_from_malformed(text)
    if fallback_text:
        return TranslationCandidate(
            bubble_id=bubble_id,
            text=fallback_text,
            rationale="",
            confidence=0.8,
            footnotes=[fn for fn in fallback_footnotes if fn.type in {"loanword", "sfx"}],
        )

    return TranslationCandidate(bubble_id=bubble_id, text=text)


def augment_footnotes_from_rationale(
    *,
    text: str,
    rationale: str,
    footnotes: list[FootnoteEntry],
) -> list[FootnoteEntry]:
    """Recover footnotes when model wrote term mappings only in rationale."""
    existing_originals = {fn.original for fn in footnotes if fn.original}
    if not rationale:
        return footnotes

    candidates = RATIONALE_TERM_RE.findall(rationale)
    for term in candidates:
        if term in existing_originals:
            continue
        if not KATAKANA_RE.search(term):
            continue
        # If translated text appears to contain Chinese loanword replacement,
        # attach a conservative footnote entry.
        if text and len(text.strip()) > 0:
            footnotes.append(
                FootnoteEntry(
                    original=term,
                    translation="见正文",
                    type="loanword",
                )
            )
            existing_originals.add(term)
    return footnotes


def extract_structured_from_malformed(
    text: str,
) -> tuple[str | None, list[FootnoteEntry]]:
    """Best-effort extractor for malformed JSON-like model outputs."""
    m_text = TEXT_FIELD_RE.search(text)
    extracted_text = None
    if m_text:
        extracted_text = unescape_json_string(m_text.group(1))

    extracted_footnotes: list[FootnoteEntry] = []
    for orig_raw, trans_raw, typ in FOOTNOTE_ITEM_RE.findall(text):
        original = unescape_json_string(orig_raw)
        translation = unescape_json_string(trans_raw)
        if original and translation:
            extracted_footnotes.append(
                FootnoteEntry(original=original, translation=translation, type=typ)
            )
    return extracted_text, extracted_footnotes


def unescape_json_string(s: str) -> str:
    try:
        return json.loads(f'"{s}"')
    except Exception:
        return s


def merge_footnotes(
    first: list[FootnoteEntry],
    second: list[FootnoteEntry],
) -> list[FootnoteEntry]:
    merged: list[FootnoteEntry] = []
    seen: set[tuple[str, str, str]] = set()
    for footnote in [*first, *second]:
        key = (footnote.original, footnote.translation, footnote.type)
        if key in seen:
            continue
        seen.add(key)
        merged.append(footnote)
    return merged


def ensure_katakana_footnotes(
    *,
    source_text: str,
    translated_text: str,
    footnotes: list[FootnoteEntry],
) -> list[FootnoteEntry]:
    """Enforce: katakana terms in source should have footnotes."""
    existing = {fn.original for fn in footnotes if fn.original}
    terms = KATAKANA_RE.findall(source_text or "")
    for term in terms:
        if term in existing:
            continue
        footnotes.append(
            FootnoteEntry(
                original=term,
                translation="见正文" if translated_text else "",
                type="loanword",
            )
        )
        existing.add(term)
    return footnotes


def normalize_name_translation(
    *,
    source_text: str,
    translated_text: str,
    glossary: dict[str, str],
) -> str:
    """Keep run-level name translation consistent for JP honorific mentions."""
    jp_matches = JP_HONORIFIC_PATTERN.findall(source_text or "")
    if not jp_matches:
        return translated_text

    key = jp_matches[0]
    current = translated_text or ""

    mapped_name = glossary.get(key)
    current_match = ZH_NAME_SUFFIX_PATTERN.search(current)
    current_name = current_match.group(1) if current_match else None

    if mapped_name is None and current_name:
        glossary[key] = current_name
        return current

    if mapped_name and current_name and mapped_name != current_name:
        return current.replace(current_name, mapped_name)

    return current


def parse_semantic_response(bubble_id: str, raw: str) -> SemanticTranslation:
    """Parse semantic translation LLM response."""
    text, parsed = parse_jsonish_response(raw)
    if isinstance(parsed, dict):
        footnotes = []
        for fn in parsed.get("footnotes", []):
            if isinstance(fn, dict):
                footnotes.append(FootnoteEntry(**fn))
        # Accept all footnote types now (including coined, cultural, fictional)
        footnotes = [fn for fn in footnotes if fn.type in {"loanword", "sfx", "coined", "cultural", "fictional"}]
        # Coerce non-string speech_act/emotion (LLM sometimes returns [] or null)
        speech_act = parsed.get("speech_act")
        if not isinstance(speech_act, str):
            speech_act = None
        emotion = parsed.get("emotion")
        if not isinstance(emotion, str):
            emotion = None
        return SemanticTranslation(
            bubble_id=bubble_id,
            text=parsed.get("text", parsed.get("translation", text)),
            speech_act=speech_act,
            emotion=emotion,
            must_preserve=[str(item) for item in parsed.get("must_preserve", [])],
            footnotes=footnotes,
            rationale=parsed.get("rationale", ""),
            confidence=float(parsed.get("confidence", 0.8)),
        )

    fallback_text, fallback_footnotes = extract_structured_from_malformed(text)
    if fallback_text:
        return SemanticTranslation(
            bubble_id=bubble_id,
            text=fallback_text,
            confidence=0.8,
            footnotes=[fn for fn in fallback_footnotes if fn.type in {"loanword", "sfx"}],
        )
    return SemanticTranslation(bubble_id=bubble_id, text=text, confidence=0.8)


def parse_persona_response(
    *,
    bubble_id: str,
    raw: str,
    semantic: SemanticTranslation,
    speaker_id: str | None,
    listener_id: str | None,
    relationship_context_used: bool,
    memory_context_used: bool,
    vision_context_used: bool,
) -> tuple[TranslationCandidate, PersonaRenderTrace]:
    """Parse persona render LLM response."""
    text, parsed = parse_jsonish_response(raw)
    rendered_text = text
    persona_moves: list[str] = []
    rationale = ""
    confidence = 0.8
    if isinstance(parsed, dict):
        rendered_text = parsed.get("text", parsed.get("translation", text))
        persona_moves = [str(item) for item in parsed.get("persona_moves", [])]
        rationale = parsed.get("rationale", "")
        confidence = float(parsed.get("confidence", 0.8))
    else:
        fallback_text, _ = extract_structured_from_malformed(text)
        if fallback_text:
            rendered_text = fallback_text

    candidate = TranslationCandidate(
        bubble_id=bubble_id,
        text=rendered_text,
        rationale=rationale,
        confidence=confidence,
        source_text=semantic.text,
    )

    trace = PersonaRenderTrace(
        bubble_id=bubble_id,
        speaker_id=speaker_id,
        listener_id=listener_id,
        relationship_context_used=relationship_context_used,
        memory_context_used=memory_context_used,
        vision_context_used=vision_context_used,
        persona_moves=persona_moves,
        rationale=rationale,
        confidence=confidence,
        source_text=semantic.text,
        original_text=rendered_text,
        final_text=rendered_text,
    )
    return candidate, trace
