# Overnight Progress 2026-06-22

## P1: Memory Character ID Fragmentation + Generic-Trash Filtering

**Branch:** `fix/p1-memory-fragmentation`
**Commit:** `b3ec0a00`
**Status:** Done — unit tests + simulation verification passing

### Problem

~80 character entries where there should be ~3-4 real characters. Same
character got 8+ IDs (variant descriptions from vision: Miko (variants),
miko_variants, etc.) + trash IDs (Narrator, Environmental, Female character,
Girl with hand to mouth, etc.). Root cause: characters created using the RAW
vision `provisional_speaker` description as the ID; `_GENERIC_SPEAKER_RE`
only blocked bare words (girl/boy/man/woman), not descriptive phrases.

### Fix (two gates)

1. **`mga/memory/speaker_filter.py`** (new) — shared module:
   - `is_generic_speaker()`: expanded filter blocking descriptive phrases
     ("Girl with X", "Female character", "Unseen speaker", "Narrator",
     "Environmental", Japanese markers, etc.) while preserving labels with
     real name tokens in parentheses
   - `extract_name_tokens()`: CJK + Latin token extraction with honorific
     stripping and generic-word filtering
   - `find_canonical_match()`: token-based matching against existing characters
   - `pick_canonical_id()`: prefers CJK token, falls back to Latin

2. **`mga/pipeline/speaker_attribution_stage.py`** — canonicalises vision-set
   `speaker_id` before translation runs:
   - Clears generic IDs (Narrator, Female character, etc.)
   - Merges variant IDs to existing characters via token index
   - Picks clean canonical IDs for new characters (e.g. CJK preferred over
     composite "miko_(variants)")
   - Uses `is_generic_speaker()` instead of the old `_GENERIC_SPEAKER_RE`

3. **`mga/memory/character_memory_updater.py`** — safety-net gate:
   - Skips generic speakers entirely (no character created)
   - Merges variant IDs to existing characters via token matching + alias
   - Creates new characters with clean canonical IDs

### Verification

- **Unit tests:** 26 new tests in `tests/memory/test_speaker_filter.py` covering:
  (a) descriptive hints rejected, (b) variant merging, (c) real names still create
- **Full suite:** 1087 passed, 1 pre-existing render failure (unrelated), 3 skipped
- **Simulation:** 10 trash IDs + 8 fragmented IDs → 3 characters (miko, miku,
  CJK-variant), 0 trash IDs. The 5 CJK-linked variants merged into 1 character.

### Files changed

- `mga/memory/speaker_filter.py` (new — 347 lines)
- `mga/memory/character_memory_updater.py` (+60 lines)
- `mga/pipeline/speaker_attribution_stage.py` (+134 lines)
- `tests/memory/test_speaker_filter.py` (new — 396 lines)
- `tests/pipeline/test_speaker_attribution_stage.py` (+2/-2 lines, assertion update)
