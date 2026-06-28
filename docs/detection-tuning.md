# Detection Parameter Tuning

Reference for tuning Pass 1 detection parameters when OCR coverage is too low (text bubbles missed) or too noisy (false detections). Salvaged from the 2026-06-24 Pass 1 fix analysis; the dated debugging narrative is archived under `docs/archive/`.

Current export default: `detection_size: 1024` (`mga/runtime_bridge/external.py`). Raise it for high-resolution scans per the table below.

## text_threshold (text confidence)
- **0.2–0.3**: high recall — low-contrast or handwritten fonts
- **0.4–0.5**: balanced — standard printed manga
- **0.6–0.8**: high precision — when avoiding false positives matters most

## box_threshold (bounding-box confidence)
- **0.4–0.5**: loose — blurry edges, irregular bubbles
- **0.6–0.7**: standard — clean bubble boundaries
- **0.8+**: strict — high-quality scans only

## detection_size (detection resolution)
- **1536**: low-resolution web manga
- **2048**: standard scans (300 dpi A5)
- **2560–3072**: high-resolution scans (600 dpi or larger format)

## unclip_ratio (box expansion ratio)
- **2.0–2.3**: tight to the text — dense typesetting
- **2.5–2.8**: leaves margin — slanted text, decorative fonts
- **3.0+**: large expansion — special-effect text (explosion/shake lettering)
