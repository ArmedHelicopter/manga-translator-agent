"""Speaker ID filtering and canonicalization.

Prevents generic/trash speaker IDs from polluting character memory and
collapses variant descriptions of the same character into a single canonical ID.

Root cause (docs/handoff-2026-06-22-memory-reassessment.md):
  Vision emits different ``provisional_speaker`` descriptions each call for the
  same character (美胡 / Miko (美胡) / miko_美胡_the_girl_with_long_hair / …).
  Without canonicalization, each variant becomes a separate character entry,
  producing ~80 entries where there should be ~3-4.  Generic descriptions
  (Female character, Girl with X, Unseen speaker, Narrator, …) also leak
  through as characters because the old ``_GENERIC_SPEAKER_RE`` only blocked
  bare words (girl/boy/man/woman/unknown), not descriptive phrases.

Two gates need this module:
  1. ``speaker_attribution_stage`` — canonicalises ``speaker_id`` before
     translation runs.
  2. ``CharacterMemoryUpdater`` — safety-net filter so generic IDs never
     persist even if attribution is bypassed.

What breaks without this module:
  - ~80 character entries for ~3-4 real characters (ID fragmentation).
  - Trash IDs (Narrator, Environmental, Girl with hand to mouth, …) persisted
    as real characters with translation observations.
"""

from __future__ import annotations

import re

from mga.memory.entities import CharacterState

# ── Generic speaker detection ───────────────────────────────────

# Bare exact-match generics (casefolded, whitespace-stripped).
# What breaks if these pass: "Narrator" and "Environmental" become characters
# with translation observations, polluting memory with non-character entries.
_GENERIC_EXACT_COMPACT = frozenset({
    # English bare words
    "unknown", "unidentified", "someone", "person", "speaker", "girl", "boy",
    "man", "woman", "child", "character", "female", "male", "narrator",
    "environmental", "environment", "none", "null", "n/a", "na", "n_a",
    # Japanese generic markers
    "未確定", "未明確", "未定", "不明", "不明確", "誰か", "人物", "登場人物",
    "語り手", "環境", "なし", "無し",
})

# Regex patterns for descriptive/placeholder IDs.
# Applied to the casefolded label WITH spaces preserved (not compact).
# What breaks if these pass: "Girl with dark hair", "Female character",
# "Unseen speaker", "Character (bottom-left panel)" all become characters.
_GENERIC_PATTERNS: list[re.Pattern[str]] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        # "Girl with …", "Boy with …", etc.
        r"^(girl|boy|man|woman|child|person|character)\s+with\s",
        # "Female character", "Male character"
        r"^(female|male)\s+character",
        # "Character with …", "Character (…)"
        r"^character\s+with\s",
        r"^character\s*\(",
        # "Unseen speaker", "Off-screen speaker", "Background speaker"
        r"^(unseen|off[-_\s]?screen|background)\s+speaker",
        # "Girl in …", "Boy in …"
        r"^(girl|boy|man|woman|child)\s+in\s",
        # "Light-haired girl", "Dark-haired boy"
        r"^\w+-haired\s+(girl|boy|man|woman)",
        # "Someone near …", "Person in …"
        r"^someone\s+near\s",
        r"^person\s+in\s",
        # "Girl with hand to mouth"
        r"^(girl|boy|man|woman)\s+with\s+hand",
        # "(environmental)", "(narrator)", "(unknown)", "(none)", "(n/a)" in parens
        r".*\((environmental|narrator|unknown|none|n/?a)\)",
        # "Hooded Figure", "Cloaked Man", "Masked Person", "Shadowy Figure"
        # What breaks if missing: "Hooded Figure" matched no pattern + had
        # extract_name_tokens={figure,hooded} → not generic → became a character.
        r"^(hooded|cloaked|masked|goggled|veiled|bandaged|shadowy|hood)\s+(figure|man|woman|girl|boy|person|character|silhouette|shadow)",
        # Bare "Figure" / "Silhouette" / "Shadow" / "Form" (descriptive, not a name)
        r"^(figure|silhouette|shadow|form)$",
        # Backward-compat with original _GENERIC_SPEAKER_RE (hyphenated forms)
        r"^unknown[-_ ].+",
        r".*[-_ ]near[-_ ].+",
        r".*[-_ ]left$",
        r".*[-_ ]right$",
    ]
]

# Japanese generic markers (substring match on casefolded label)
_GENERIC_JP_MARKERS = ("未確定", "未明確", "語り手", "登場人物")

# ── Name-token extraction ───────────────────────────────────────

# CJK character ranges: Hiragana, Katakana, CJK Unified Ideographs,
# CJK Extension A, CJK Compatibility Ideographs.
_CJK_RE = re.compile(
    r"[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]+"
)

# Latin word tokens (2+ letters, no digits)
_LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")

# Parenthetical content
_PARENS_RE = re.compile(r"\(([^)]*)\)")

# CJK honorific suffixes to strip before token extraction.
# What breaks if not stripped: "美胡ちゃん" and "美胡" would be treated as
# different tokens, fragmenting the same character.
_CJK_HONORIFICS = ("ちゃん", "くん", "さん", "様", "先生", "先輩", "殿", "氏")

# Latin honorific suffixes to strip (with leading hyphen).
_LATIN_HONORIFICS = (
    "-chan", "-kun", "-san", "-sama", "-sensei", "-senpai", "-sama",
)

# CJK sequences that are generic markers, not names.
_GENERIC_CJK = frozenset({
    "未確定", "未明確", "未定", "不明", "不明確", "誰か",
    "人物", "登場人物", "語り手", "環境", "なし", "無し",
})

# Latin words that are descriptive, not names.  Used to filter token extraction
# so that "Girl with dark hair" yields no Latin tokens (only CJK tokens, if any).
_GENERIC_LATIN = frozenset({
    # Generic speaker descriptors
    "girl", "boy", "man", "woman", "child", "person", "character", "female",
    "male", "speaker", "unseen", "off", "screen", "offscreen", "background",
    "unknown", "unidentified", "someone", "narrator", "environmental",
    "environment", "none", "null", "near", "left", "right",
    # Physical description words
    "hair", "dark", "light", "long", "short", "blonde", "black", "white",
    "red", "brown", "blue", "green", "haired",
    # Positional / panel words
    "close", "up", "likely", "panel", "facing", "forward", "bottom", "top",
    # Action / annotation words
    "calling", "hand", "mouth", "thought", "thinking", "voice", "narration",
    "description", "kimono", "door",
    # Common English stop words (2+ letters)
    "the", "an", "of", "to", "and", "or", "for", "from", "this", "that",
    "his", "her", "their", "with", "in", "on", "at", "by",
    # Generic forms
    "na",
    # Descriptive nouns/adjectives that are NOT names — these leaked as fake
    # "name tokens" before this stoplist covered them, so descriptive labels
    # like "Character (likely the one with the braided hair)" / "Hooded Figure"
    # passed is_generic_speaker and became characters. Root cause:
    # extract_name_tokens / _has_name_tokens treated any non-stoplist Latin
    # word as a name. See docs/handoff-2026-06-22-memory-reassessment.md.
    "figure", "silhouette", "shadow", "form", "hooded", "hood", "cloak",
    "cloaked", "cape", "masked", "veiled", "bandaged", "goggled", "shadowy",
    "braided", "braid", "ponytail", "ponytailed", "glasses",
    # Number / ordinal words (not names)
    "one", "two", "three", "four", "first", "second", "third",
    # Vague reference words (not names)
    "other", "another", "same", "nearby", "young", "old", "tall", "small",
    "large", "big", "little", "several", "some",
})


def _normalize_compact(label: str) -> str:
    """Casefold and strip ALL whitespace for exact-match comparisons."""
    return re.sub(r"\s+", "", str(label).strip().casefold())


def _normalize_folded(label: str) -> str:
    """Casefold and collapse whitespace to single spaces for pattern matching."""
    return re.sub(r"\s+", " ", str(label).strip().casefold())


def _strip_honorifics(text: str) -> str:
    """Remove CJK and Latin honorific suffixes from a speaker label."""
    for h in _CJK_HONORIFICS:
        text = text.replace(h, "")
    for h in _LATIN_HONORIFICS:
        text = text.replace(h, "")
    return text


# ── Public API ──────────────────────────────────────────────────


def is_generic_speaker(label: str) -> bool:
    """Return True if *label* is a generic/placeholder speaker ID.

    A label is generic if it matches a known generic pattern (bare word,
    descriptive phrase, or Japanese marker) AND contains no extractable
    name tokens.  Labels like "Girl with dark hair (Miho)" are NOT generic
    because the parenthetical "Miho" is a name token — the caller should
    canonicalise to "Miho" instead of discarding.
    """
    if not label or not label.strip():
        return True

    folded = _normalize_folded(label)
    compact = _normalize_compact(label)

    # Exact-match generics (always generic, regardless of name tokens)
    if compact in _GENERIC_EXACT_COMPACT:
        return True

    # Japanese generic markers (substring)
    for marker in _GENERIC_JP_MARKERS:
        if marker in folded:
            return True

    # Descriptive patterns — generic only if NO name tokens are extractable.
    # "Girl with dark hair (Miho)" matches a pattern but has "miho" in parens
    # → not generic (canonicalise to "miho" instead).
    # "Character with glasses" matches a pattern and has no name tokens → generic.
    for pattern in _GENERIC_PATTERNS:
        if pattern.match(folded):
            if _has_name_tokens(label):
                return False
            return True

    return False


def _has_name_tokens(label: str) -> bool:
    """Check if a label has any name tokens (CJK or parenthetical Latin).

    Used by is_generic_speaker to decide whether a descriptive-pattern match
    is truly generic.  Only CJK sequences and Latin words inside parentheses
    count — Latin words in the main label body (e.g. "glasses" in "Character
    with glasses") are descriptive, not names.
    """
    if not label:
        return False
    text = _strip_honorifics(label.strip())
    # CJK sequences are always potential names
    for match in _CJK_RE.finditer(text):
        if match.group() not in _GENERIC_CJK:
            return True
    # Latin words from parenthetical content (high confidence of being a name)
    for paren_match in _PARENS_RE.finditer(text):
        for word in _LATIN_WORD_RE.findall(paren_match.group(1)):
            if word.lower() not in _GENERIC_LATIN:
                return True
    return False


def extract_name_tokens(label: str) -> set[str]:
    """Extract proper-noun tokens from a speaker label for canonical matching.

    CJK sequences are the most reliable signal: if two labels share a CJK
    token (e.g. 美胡), they refer to the same character.  Latin words that
    are not in the generic-descriptor stoplist are also extracted, primarily
    from parenthetical content and underscore-separated composites.

    Examples:
        "Miko (美胡)"                → {"miko", "美胡"}
        "miko_美胡_the_girl_with_long_hair" → {"miko", "美胡"}
        "美胡ちゃん (Miko-chan)"      → {"miko", "美胡"}
        "Girl with dark hair (Miho)" → {"miho"}
        "Narrator"                   → {} (no tokens)
    """
    if not label:
        return set()

    text = _strip_honorifics(label.strip())
    tokens: set[str] = set()

    # CJK sequences — the primary matching signal
    for match in _CJK_RE.finditer(text):
        cjk = match.group()
        if cjk not in _GENERIC_CJK:
            tokens.add(cjk)

    # Latin words (2+ letters, not in generic stoplist)
    for word in _LATIN_WORD_RE.findall(text):
        w = word.lower()
        if w not in _GENERIC_LATIN:
            tokens.add(w)

    return tokens


def build_token_index(characters: list[CharacterState]) -> dict[str, str]:
    """Build a {token → character_id} lookup from existing characters.

    The index maps every name token (from character_id, name_jp, name_zh,
    and provenance aliases) to the character's canonical ID.  First token
    wins (earliest character in the list takes precedence).
    """
    index: dict[str, str] = {}
    for char in characters:
        labels: list[str] = []
        if char.character_id:
            labels.append(char.character_id)
        if char.name_jp:
            labels.append(char.name_jp)
        if char.name_zh:
            labels.append(char.name_zh)
        aliases = char.provenance.get("aliases", [])
        if isinstance(aliases, list):
            labels.extend(str(a) for a in aliases)
        for label in labels:
            for token in extract_name_tokens(label):
                if token not in index:
                    index[token] = char.character_id
    return index


def find_canonical_match(
    label: str, token_index: dict[str, str]
) -> str | None:
    """Return the character_id of an existing character that matches *label*.

    Matching is by shared name token: if any token extracted from *label*
    appears in *token_index*, the corresponding character_id is returned.
    Returns None if no match is found.
    """
    tokens = extract_name_tokens(label)
    if not tokens:
        return None
    # Prefer CJK tokens first (most reliable), then Latin tokens
    cjk_tokens = sorted(
        (t for t in tokens if _CJK_RE.match(t)), key=len
    )
    for token in cjk_tokens:
        if token in token_index:
            return token_index[token]
    latin_tokens = sorted(
        (t for t in tokens if not _CJK_RE.match(t)), key=len
    )
    for token in latin_tokens:
        if token in token_index:
            return token_index[token]
    return None


def pick_canonical_id(label: str) -> str:
    """Choose the cleanest canonical ID from a raw speaker label.

    Preference order:
    1. Shortest CJK token (base name without honorifics)
    2. Shortest Latin token (casefolded)
    3. Normalized label (whitespace-stripped, casefolded) as fallback
    """
    tokens = extract_name_tokens(label)
    if tokens:
        cjk_tokens = [t for t in tokens if _CJK_RE.match(t)]
        if cjk_tokens:
            return min(cjk_tokens, key=len)
        latin_tokens = [t for t in tokens if not _CJK_RE.match(t)]
        if latin_tokens:
            return min(latin_tokens, key=len)
    return _normalize_compact(label)


def resolve_speaker(
    label: str, token_index: dict[str, str]
) -> str | None:
    """Resolve a speaker label to a canonical character ID.

    Returns:
        - An existing character_id if *label* matches via name tokens.
        - A clean canonical ID (from ``pick_canonical_id``) if *label* is
          non-generic but has no existing match.
        - None if *label* is generic (caller should skip attribution).
    """
    if is_generic_speaker(label):
        return None
    existing = find_canonical_match(label, token_index)
    if existing:
        return existing
    return pick_canonical_id(label)
