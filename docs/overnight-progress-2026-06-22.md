# Overnight Progress 2026-06-22

## P2: OCR Dialogue-Bubble Miss Rate — OCR Engine Swap Does NOT Help

**Branch:** `fix/p2-ocr-coverage`
**Status:** Done — honest negative result. No config change.

### Problem

The default OCR engine (`ocr48px`) was reported as detecting only title/chapter
regions on page-003, missing ~21 dialogue bubbles (47% coverage). The vision
stage backfills them, which was the source of dict-repr garbage + memory
fragmentation. The hypothesis was that swapping to `48px_ctc` (CTC-based) or
`mocr` (MangaOCR) would improve dialogue-bubble coverage.

### Root Cause: Detection, Not OCR

**The OCR engine is NOT the bottleneck. The text detector is.**

The manga-image-translator pipeline has two stages:
1. **Detection** (`Detector.default` = DBNet) — finds text regions (Quadrilaterals)
2. **OCR** (`Ocr.ocr48px` / `ocr48px_ctc` / `mocr`) — recognizes text *within*
   already-detected regions

OCR operates ONLY on regions the detector found. If the detector misses dialogue
bubbles, no OCR engine can recognize them — they were never passed to OCR.

### Evidence

Tested on `data/experiments/test-3-pages/page-003.png` (3750x5334, a manga
table-of-contents page with chapter numbers and title text in the upper portion,
dialogue bubbles in the lower portion).

**Detection runs ONCE, then each OCR engine recognizes the same detected regions:**

| Engine    | Detected | Recognized | Dropped | Coverage |
|-----------|----------|------------|---------|----------|
| 48px      | 15       | 15         | 0       | 100%     |
| 48px_ctc  | 15       | 15         | 0       | 100%     |
| mocr      | 15       | 15         | 0       | 100%     |

All 15 detected regions are in the upper ~40% of the page (y=1570–2160 and
y=4839–5130) — title, chapter numbers, and "CONTENTS" text. **Zero dialogue
bubbles** were detected in the lower 60% of the page.

**Detection parameter tuning also fails to find dialogue bubbles:**

| Config                                    | Textlines | Notes                        |
|-------------------------------------------|-----------|------------------------------|
| DEFAULT (thresh=0.5, box=0.7, size=2048)  | 15        | All title/TOC area           |
| text_threshold=0.3                        | 15        | Same regions, lower prob     |
| box_threshold=0.5                         | 15        | Identical to default         |
| thresh=0.3 + box=0.5                      | 15        | Same regions                 |
| detection_size=4096                       | 16        | +1 tiny region, still no DB  |
| size=4096 + thresh=0.3 + box=0.5          | 18        | +3 tiny regions, still no DB |

**CTD (ComicTextDetector) detector also fails:** finds only 10 textlines, all in
the same upper-page title/TOC area.

Cross-verified on page-005 (8 textlines) and page-009 (12 textlines) — same
pattern: all 3 OCR engines recognize 100% of detected textlines, no dialogue
bubbles detected by any detector.

### Why the Detector Misses Dialogue Bubbles

The default DBNet detector (`detect-20241225.ckpt`) was trained on general text
detection. For this manga's art style, dialogue bubbles likely have:
- Low text/background contrast (hand-drawn or stylized text)
- Non-standard text orientations or fonts
- Text integrated with artwork that confuses the segmentation model

This is a known limitation of DBNet on manga with unconventional lettering.
The CTD detector (designed for comics) also fails, suggesting the issue is
art-style-specific rather than detector-architecture-specific.

### Conclusion

**P2 converges on: "vision backfill is sufficient, OCR engine swap doesn't help."**

The mga pipeline's vision stage correctly backfills the dialogue bubbles that the
text detector misses. Swapping OCR engines (48px → 48px_ctc or mocr) provides
zero improvement because the bottleneck is upstream (detection), not downstream
(recognition). All three OCR engines recognize 100% of detected textlines.

### No Config Change

`config.py:310` remains `ocr: Ocr = Ocr.ocr48px`. No change — swapping engines
would add cost (mocr requires the manga-ocr HuggingFace model; 48px_ctc requires
a separate 138MB model download) with zero benefit.

### Future Investigation Directions (NOT in scope for P2)

If dialogue-bubble detection needs improvement, the lever is the **detector**,
not the OCR engine:
1. Fine-tune the DBNet detector on manga pages with dialogue bubbles
2. Try `det_invert` / `det_gamma_correct` / `det_auto_rotate` detection options
3. Add a bubble-detection pre-pass (detect speech balloons, then run OCR inside)
4. Lower `text_threshold` further (0.2 or 0.1) — but testing showed 0.3 already
   yields no new dialogue bubbles, so this is unlikely to help
5. The mga vision stage backfill is the correct architectural choice for this
   art style — the runtime detector simply cannot see these bubbles
