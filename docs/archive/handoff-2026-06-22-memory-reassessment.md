# Memory Cold-Start Reassessment (2026-06-22)

> **Corrects `docs/handoff-2026-06-19-pipeline-run.md`'s "speaker_id all-null, memory empty" conclusion.**
> That conclusion was true on 06-19 but is **obsolete** as of the 06-21 e2e run.

## TL;DR

- The 06-19 handoff said `speaker_id` was all-null and `memory/character profiles` were empty.
- The **2026-06-21** e2e run on `data/input/test-pdf-10pages/` shows memory is **non-empty**:
  ~80 character entries, and `CharacterMemoryUpdater` is **active** (real profiles with voice
  evolution + translation observations).
- The principal contradiction has moved: it is no longer "nothing is created", it is
  **ID fragmentation + generic-trash IDs**.
- The same-day `speaker_attribution` cold-start-create fix targets the *obsolete* contradiction.
  It is a neutral defensive backstop, **not** the remedy for the current one.

## Evidence (read directly, not inferred)

`data/input/test-pdf-10pages/memory/state/index.json` — `last_updated: 2026-06-21T19:11:45`, 80 character keys.

`characters/美胡.json` — a real, live profile:
- `speech_patterns.latest_source_sample`, `tone_spectrum.latest_tone: contemplative`
- `provenance.translation_observations`: 5 entries from `page_0009` (bubble ids `vision-0009-*`),
  each with source_text + translated_text
- `provenance.last_updated_page: page_0009`

`characters/Miku.json` — `voice_evolutions` with `timestamp: 2026-06-21T16:31:42`,
`translation_observations` from `page_0008` bubble `region-0008-0003`.

The `provenance.translation_observations` fingerprint = `CharacterMemoryUpdater.update_from_translation`
(`mga/memory/character_memory_updater.py`), invoked from `translation_stage.py:589/826` when
`speaker` is non-empty. So the creation/update path that 06-19 reported as dead is **alive**.

## New principal contradiction: fragmentation + trash

### 1. ID fragmentation (same character, many IDs)
The character "美胡 / Miko / the long-haired girl" is spread across **8+ separate entries**:
`美胡`, `Miku`, `Miku (thought)`, `Miko (美胡)`, `Miko (the girl with long hair)`,
`miko_美胡_the_girl_with_long_hair`, `美胡ちゃん (Miko-chan)`, `long-haired girl (美胡ちゃん)`,
`Girl with dark hair (Miho)`, `Light-haired girl (calling Miho)`.

Root cause: characters are created using the **raw vision `provisional_speaker` description as
the ID**. Vision emits a different description each call, so each variant becomes a new character.
No canonicalization, no alias merging.

### 2. Generic-trash IDs not filtered
`_GENERIC_SPEAKER_RE` only blocks bare words (`girl|boy|man|woman|unknown|someone|...`). It does
**not** block descriptive/placeholder IDs that vision happily emits:
`Female character`, `Female character (blonde hair, kimono)`, `Girl with hand to mouth`,
`Girl in close-up (likely)`, `Unseen speaker`, `Off-screen speaker`, `Narrator`,
`Environmental`, `none`, `n_a`, `N/A (environmental)`, `未確定`, `未明確`, `Character with glasses`,
`Character (bottom-left panel, facing forward)`, etc. These all became persisted characters.

## Re-positioning the same-day speaker_attribution cold-start fix

- Targets the 06-19 failure mode: vision emits **no** `provisional_speaker` at all → `speaker_id`
  stays null → nothing created.
- But 06-21 shows vision **is** emitting (descriptive) speakers, and `translation_stage` is
  creating/updating from them. So the "completely empty" mode did not recur.
- Verdict: **neutral defensive backstop** for the extreme case, not the remedy for fragmentation.
- Residual risk: its generic guard is too loose — `Female character` / `Girl with X` pass and
  would get a normalized new ID if `speaker_attribution` runs first. Whether this **adds**
  duplicates on top of the `translation_stage` path needs an e2e re-run to confirm
  (the 3 unit tests pass, but they only exercise the stage in isolation).

## What actually needs doing (listed as TODOs — doc-only this round, no code changed)

Ranked by ROI:

1. **Tighten generic filtering.** Expand the rejection set to cover descriptive/placeholder IDs:
   `Female character`, `Girl with ...`, `Boy with ...`, `Unseen speaker`, `Off-screen speaker`,
   `Narrator`, `Environmental`, `none`, `n_a`, `N/A`, `未確定`, `未明確`, any ID that is a pure
   description (no proper-noun token). Locations: `speaker_attribution_stage._GENERIC_SPEAKER_RE`
   **and** the `translation_stage` / `CharacterMemoryUpdater` creation gate (two gates, because
   creation currently flows through the updater, not speaker_attribution).
2. **ID canonicalization / alias merging.** Collapse the 8+ IDs for one character into a single
   canonical id + `aliases[]`. Likely a post-translation character-merge step, or normalize at
   creation time against an alias map seeded from vision hints. This is the bigger structural fix.
3. **Confirm whether speaker_attribution running before translation helps or hurts.** If vision's
   descriptions were consistent, normalize (casefold + whitespace strip) would merge case/space
   variants — but 06-21 shows descriptions vary semantically, so normalize alone won't merge
   "美胡" with "Miko (美胡)". Needs an e2e re-run to measure.

## Creation-path confirmation

The 06-21 character files have `provenance.translation_observations` but **no `source` field**
(the `speaker_attribution` cold-start helper stamps `provenance.source: cold_start_speaker_hint`).
So none of these 80 characters came from the new `speaker_attribution` branch — they all came
from `CharacterMemoryUpdater.update_from_translation`. This confirms the 06-19 → 06-21 transition:
something between those dates made `speaker` non-empty in `translation_stage` (vision started
emitting `provisional_speaker`, or a seeding path activated), and the updater then ran.

## Implication for the audit narrative

`docs/STATUS.md` and memory `doc-trust-hierarchy` previously ranked Character Consistency at
"L1, speaker_id all-null, memory空转". That is updated to **L2**: memory is non-empty and the
updater is active, but quality is blocked by fragmentation + trash. The headline-value feature
is no longer "空转" — it is "running dirty".
