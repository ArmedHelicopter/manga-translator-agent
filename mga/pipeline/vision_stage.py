"""Stage 2 -- OCR artifact loading plus Vision enrichment."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from mga.models import BoundingBox, Bubble, ProjectConfig, VisualFootnote
from mga.ocr import BlankPageDetector, OCRGuardConfig, RecoveryOrchestrator
from mga.providers import ProviderCascade

from .stages import PipelineContext, PipelineStage

logger = logging.getLogger(__name__)


def _compute_iou(bbox_a: "BoundingBox", bbox_b: "BoundingBox") -> float:
    """Axis-aligned bounding box IoU."""
    x1 = max(bbox_a.x, bbox_b.x)
    y1 = max(bbox_a.y, bbox_b.y)
    x2 = min(bbox_a.x + bbox_a.width, bbox_b.x + bbox_b.width)
    y2 = min(bbox_a.y + bbox_a.height, bbox_b.y + bbox_b.height)
    if x2 <= x1 or y2 <= y1:
        return 0.0
    inter = (x2 - x1) * (y2 - y1)
    area_a = bbox_a.width * bbox_a.height
    area_b = bbox_b.width * bbox_b.height
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return inter / union


def _text_overlap(a: str, b: str) -> float:
    """Jaccard-like character-level text overlap between two strings.

    Returns a float in [0, 1] where 1 means the strings share all unique
    characters. Used by the vision hallucination guard to check whether a
    vision bubble's source_text has any textual support in the page's OCR
    text.
    """
    if not a or not b:
        return 0.0
    set_a = set(a)
    set_b = set(b)
    if not set_a:
        return 0.0
    intersection = set_a & set_b
    return len(intersection) / len(set_a)


def _longest_common_substring_ratio(a: str, b: str) -> float:
    """Ratio of longest common substring to the shorter string length.

    More adversarial than character-set overlap: two texts can share 80% of
    their character sets (e.g. 「私は猫です」 and 「僕は犬です」 both contain
    「は」「です」) without being semantically related.  LCS catches real
    phrase-level borrowing across pages, which is the cross-page bleed
    signature.

    Returns a float in [0, 1] where 1 means one string is a substring of
    the other.
    """
    if not a or not b:
        return 0.0
    # Use the shorter string as the needle, longer as the haystack.
    needle, haystack = (a, b) if len(a) <= len(b) else (b, a)
    if len(needle) < 3:
        # Below 3 characters any LCS match is noise.
        return 0.0
    # Dynamic programming LCS (O(n*m)). Roughly 3.5 μs per char-pair for
    # CJK text on modern CPUs, so ~10ms for a pair of 50-char strings.
    # Acceptable: called only for long vision texts (len > 10) and only
    # once per page during validation.
    n, m = len(needle), len(haystack)
    prev = [0] * (m + 1)
    max_len = 0
    for i in range(1, n + 1):
        curr = [0] * (m + 1)
        for j in range(1, m + 1):
            if needle[i - 1] == haystack[j - 1]:
                curr[j] = prev[j - 1] + 1
                if curr[j] > max_len:
                    max_len = curr[j]
            # else: curr[j] stays 0 (no reset needed — we only track max)
        prev = curr
    return max_len / len(needle)


def _cross_page_bleed_check(
    source_text: str,
    current_page_id: str,
    current_page_ocr: set[str],
    all_pages_ocr: dict[str, set[str]],
    *,
    char_overlap_min: float = 0.2,
    lcs_ratio_min: float = 0.25,
) -> str | None:
    """Check whether *source_text* is a cross-page bleed from another page.

    Returns the ``page_id`` of the best-match page if the text has both:
    1. Higher **character overlap** with a neighbor page than the current page
    2. A **longest-common-substring** match of at least 25% of the text against
       that neighbor (catches actual phrase borrowing, not just shared
       characters)

    Returns ``None`` if the text passes — it belongs on this page.
    """
    if not source_text or not all_pages_ocr:
        return None

    cleaned = source_text.strip()
    if len(cleaned) <= 10:
        # Short texts lack enough signal for reliable bleed detection.
        return None

    # Score against current page first.
    best_page = current_page_id
    best_char_overlap = max(
        (_text_overlap(cleaned, ocr_line) for ocr_line in current_page_ocr),
        default=0.0,
    )

    # Score against every other page.
    best_neighbor_overlap = 0.0
    best_neighbor_id: str | None = None
    for page_id, ocr_set in all_pages_ocr.items():
        if page_id == current_page_id:
            continue
        page_max = max(
            (_text_overlap(cleaned, ocr_line) for ocr_line in ocr_set),
            default=0.0,
        )
        if page_max > best_neighbor_overlap:
            best_neighbor_overlap = page_max
            best_neighbor_id = page_id

    if best_neighbor_id is None:
        return None

    # Must have stronger overlap with neighbor than current page,
    # AND neighbor overlap must exceed the minimum threshold.
    if best_neighbor_overlap <= char_overlap_min:
        return None
    if best_neighbor_overlap <= best_char_overlap:
        return None

    # LCS confirmation: verify the text shares a real phrase with the neighbor,
    # not just a coincidental character-set overlap.
    neighbor_lines = all_pages_ocr.get(best_neighbor_id, set())
    best_lcs = max(
        (_longest_common_substring_ratio(cleaned, line) for line in neighbor_lines),
        default=0.0,
    )
    if best_lcs < lcs_ratio_min:
        return None

    return best_neighbor_id


def _build_vision_prompt() -> str:
    return (
        "Analyze this manga page. Your job is to identify ALL visible text regions.\n\n"
        "For EACH text region you can see (dialogue bubbles, narration boxes, SFX, signs, "
        "whispered text, small text, handwritten notes, chapter titles, cover titles), provide:\n"
        "- source_text: the Japanese/Chinese text exactly as written\n"
        "- bbox: {x, y, width, height} in pixel coordinates relative to the full image\n"
        "- box_type: dialogue, narration, sfx, sign, letter, graffiti, chapter_title, "
        "cover_title, or other\n"
        "- provisional_speaker: visible speaker label if identifiable\n"
        "- voice_hint: speech style hints (politeness, catchphrases, tone, register)\n"
        "- confidence: 0.0-1.0 how confident you are in the text extraction\n"
        "- reading_order: integer reading order (right-to-left, top-to-bottom for manga)\n"
        "- tone: emotional tone if visually inferable\n"
        "- notes: any relevant context\n\n"
        "IMPORTANT: Report ALL text you can see, even small or stylized text. Do not skip any.\n"
        "For cover pages: identify the main title as 'cover_title' with a SINGLE bounding box "
        "covering the ENTIRE title phrase, even if it spans multiple visual clusters. "
        "The full title text should be in a single source_text field for coherent translation.\n"
        "Also report visual_footnotes for author-drawn elements that need translation context.\n\n"
        "Return JSON: {bubbles: [...], visual_footnotes: [...], voice_hints: [...], scene_summary: str}"
    )


class OCRArtifactStage(PipelineStage):
    """Load OCR text regions from runtime artifacts."""

    @property
    def name(self) -> str:
        return "ocr_artifact"

    @property
    def order(self) -> int:
        return 20

    def execute(self, context: PipelineContext) -> PipelineContext:
        payload_dir = context.metadata.get("artifact_payload_dir")
        if not payload_dir:
            context.artifacts[self.name] = {
                "source": "none",
                "mode": "skipped",
                "note": "No runtime payload; Vision enrichment may run in degraded extraction mode.",
            }
            return context
        return self._execute_from_artifact(context, payload_dir)

    def _execute_from_artifact(self, context: PipelineContext, payload_dir: str) -> PipelineContext:
        """Read OCR results from runtime-exported per-page artifacts."""
        payload_path = Path(payload_dir)

        # Find all per-page artifact files
        pages_manifest = payload_path / "pages.json"
        if pages_manifest.exists():
            import json as _json
            pages_list = _json.loads(pages_manifest.read_text(encoding="utf-8"))
        else:
            # Fallback: single artifact.json
            pages_list = [{"page_index": 0, "artifact": "artifact.json"}]

        for page_entry in pages_list:
            artifact_file = payload_path / page_entry["artifact"]
            if not artifact_file.exists():
                continue

            artifact_data = json.loads(artifact_file.read_text(encoding="utf-8"))
            regions = artifact_data.get("text_regions", [])
            page_idx = page_entry["page_index"]

            # Match to existing page or create one
            page = None
            for p in context.pages:
                if p.page_index == page_idx:
                    page = p
                    break
            if not page and page_idx < len(context.pages):
                page = context.pages[page_idx]
            if not page:
                continue

            for i, region in enumerate(regions):
                lines = region.get("lines", [])
                bbox = BoundingBox()
                if lines:
                    import numpy as np
                    pts = np.array(lines).reshape(-1, 2)
                    x_min, y_min = pts.min(axis=0)
                    x_max, y_max = pts.max(axis=0)
                    bbox = BoundingBox(
                        x=float(x_min), y=float(y_min),
                        width=float(x_max - x_min), height=float(y_max - y_min),
                    )

                page.bubbles.append(Bubble(
                    bubble_id=f"region-{page_idx:04d}-{i:04d}",
                    bbox=bbox,
                    source_text=region.get("text", ""),
                    reading_order=i,
                ))

            page.scene_summary = f"Page with {len(regions)} text regions (from runtime OCR)"

        total_regions = sum(len(p.bubbles) for p in context.pages)
        context.artifacts[self.name] = {
            "source": "artifact",
            "payload_dir": payload_dir,
            "pages": len(pages_list),
            "regions": total_regions,
        }

        # OCR guard check
        self._check_ocr_guard(context)

        return context

    def _check_ocr_guard(self, context: PipelineContext) -> None:
        """Check for blank OCR pages and trigger recovery if needed."""
        cfg: ProjectConfig = context.project_config
        guard_cfg_raw = getattr(cfg, "ocr_guard", None)
        if not guard_cfg_raw:
            return

        guard_cfg = OCRGuardConfig.model_validate(guard_cfg_raw) if isinstance(guard_cfg_raw, dict) else guard_cfg_raw
        if not guard_cfg.enabled:
            return

        detector = BlankPageDetector(guard_cfg)
        sequence = detector.check_sequence(context.pages)
        if not sequence:
            return

        context.ocr_guard_state["blank_sequence"] = sequence.model_dump(mode="json")
        orchestrator = RecoveryOrchestrator(guard_cfg)
        decision = orchestrator.prompt_user(sequence, context)
        _, retry = orchestrator.apply_strategy(decision, context)
        if retry:
            from mga.exceptions import RestartPipelineSignal
            raise RestartPipelineSignal(
                reason="OCR guard triggered pipeline restart",
                new_ocr_model=decision.new_ocr_model,
            )


class VisionEnrichmentStage(PipelineStage):
    """Add non-authoritative visual context without replacing OCR text."""

    @property
    def name(self) -> str:
        return "vision"

    @property
    def order(self) -> int:
        return 25

    def execute(self, context: PipelineContext) -> PipelineContext:
        cfg: ProjectConfig = context.project_config
        has_ocr_bubbles = any(page.bubbles for page in context.pages)
        if has_ocr_bubbles:
            return self._enrich_with_vision(context, cfg, source="ocr-artifact")
        # An OCR payload with zero text_regions is not enough to render: Pass 1
        # may still have erased the source text, and render_only() needs bbox
        # seats. Falling through to vision-only extraction gives no-text OCR
        # pages recoverable geometry instead of producing empty speech bubbles.
        return self._execute_from_llm(context, cfg)

    @staticmethod
    def _vision_capable(cfg: ProjectConfig) -> bool:
        """Probe whether the configured vision provider can take image input.

        Cheap (no API call): reads the provider's ``supports_vision`` flag.
        Returns False for text-only models so we skip image work instead of
        burning one failed call per page.
        """
        try:
            return ProviderCascade(cfg, "vision").supports_vision()
        except Exception:  # noqa: BLE001 - probe must never raise.
            return False

    def _execute_from_llm(self, context: PipelineContext, cfg: ProjectConfig) -> PipelineContext:
        """Original LLM vision extraction path."""
        if not self._vision_capable(cfg):
            warning = (
                "Vision extraction skipped: configured vision provider does not "
                "support image input. Continuing with no bubbles for these pages."
            )
            logger.warning(warning)
            context.artifacts[self.name] = {
                "source": "llm",
                "mode": "vision-only-degraded",
                "enrichment": "skipped",
                "warning": warning,
            }
            return context

        provider_cascade = ProviderCascade(cfg, "vision")

        extractions: list[dict] = []
        provider_errors: list[dict] = []
        provider_calls: list[dict] = []
        for page in context.pages:
            result = self._extract_page(provider_cascade, page, cfg)
            extractions.append(result)
            self._apply_to_page(page, result)
            provider_errors.extend(provider_cascade.errors)
            provider_cascade.errors.clear()
            provider_calls.extend(provider_cascade.calls)
            provider_cascade.calls.clear()

        context.artifacts[self.name] = {
            "source": "llm",
            "mode": "vision-only-degraded",
            "extractions": extractions,
            "provider_cascade_errors": provider_errors,
            "provider_cascade_calls": provider_calls,
        }
        return context

    def _enrich_with_vision(
        self,
        context: PipelineContext,
        cfg: ProjectConfig,
        *,
        source: str,
    ) -> PipelineContext:
        if not self._vision_capable(cfg):
            warning = (
                "Vision enrichment skipped: configured vision provider does not "
                "support image input. Continuing with OCR-only bubbles."
            )
            logger.warning(warning)
            print(f"[mga] WARNING: {warning}", flush=True)
            existing = dict(context.artifacts.get(self.name, {}))
            existing.update({
                "source": source,
                "enrichment": "skipped",
                "warning": warning,
            })
            context.artifacts[self.name] = existing
            return context

        # Build cross-page OCR inventory before the vision loop.  Each page's
        # OCR bubbles are already loaded (per-pass1 or previous stage), so we
        # can collect a per-page set of known source_texts for adversarial
        # cross-page bleed detection.
        all_pages_ocr: dict[str, set[str]] = {}
        for page in context.pages:
            page_id = getattr(page, "page_id", "")
            if not page_id:
                continue
            all_pages_ocr[page_id] = {
                bubble.source_text
                for bubble in page.bubbles
                if bubble.source_text and bubble.detection_source != "vision"
            }

        provider_cascade = ProviderCascade(cfg, "vision")
        enrichments: list[dict] = []
        errors: list[dict] = []
        provider_errors: list[dict] = []
        provider_calls: list[dict] = []
        for page in context.pages:
            try:
                result = self._extract_page(provider_cascade, page, cfg)
                enrichments.append({"page_id": page.page_id, "result": result})
                self._apply_enrichment_to_page(page, result, all_pages_ocr=all_pages_ocr)
                provider_errors.extend(provider_cascade.errors)
                provider_cascade.errors.clear()
                provider_calls.extend(provider_cascade.calls)
                provider_cascade.calls.clear()
            except Exception as exc:
                errors.append({"page_id": page.page_id, "error": str(exc)})

        existing = dict(context.artifacts.get(self.name, {}))
        total_supplemented = sum(getattr(p, "_vision_supplemented", 0) for p in context.pages)
        existing.update({
            "source": source,
            "enrichment": "vision",
            "enriched_pages": len(enrichments),
            "vision_supplemented_bubbles": total_supplemented,
        })
        if errors:
            existing["enrichment_errors"] = errors
            if not enrichments:
                existing["enrichment"] = "skipped"
                existing["note"] = "Vision enrichment unavailable; continuing with OCR artifact text."
        if provider_errors:
            existing["provider_cascade_errors"] = provider_errors
        if provider_calls:
            existing["provider_cascade_calls"] = provider_calls
        if context.pages and not provider_calls:
            # Zero successful vision calls across every page is virtually always a
            # config/capability problem (e.g. a text-only model configured for the
            # vision stage) — make it loud instead of burying it in run.json.
            sample = provider_errors[0] if provider_errors else (errors[0] if errors else {})
            warning = (
                "Vision enrichment made 0 successful provider calls across "
                f"{len(context.pages)} page(s); proceeding with OCR-only bubbles. "
                "This usually means the configured vision model cannot accept "
                f"image input. First error: {sample}"
            )
            existing["warning"] = warning
            logger.warning(warning)
            print(f"[mga] WARNING: {warning}", flush=True)
        context.artifacts[self.name] = existing
        return context

    VISION_MAX_IMAGE_DIM = 2048  # max dimension for images sent to vision models

    @classmethod
    def _resize_and_get_scale(cls, image_bytes: bytes) -> tuple[bytes, float, float]:
        """Resize image to a known max dimension and return (resized_bytes, scale_x, scale_y).

        The scale factors map coordinates from the *resized* image back to the
        *original* image:  orig_x = resized_x * scale_x.

        Best-effort: if the bytes cannot be decoded as an image (corrupt file,
        non-image fixture, unsupported format), the original bytes are returned
        with unit scale so the caller still has something to send to the vision
        provider. Resize is an optimization, never fatal.
        """
        from PIL import Image as PILImage
        import io as _io

        try:
            with PILImage.open(_io.BytesIO(image_bytes)) as img:
                w, h = img.size
                if max(w, h) <= cls.VISION_MAX_IMAGE_DIM:
                    return image_bytes, 1.0, 1.0

                ratio = cls.VISION_MAX_IMAGE_DIM / max(w, h)
                new_w = int(w * ratio)
                new_h = int(h * ratio)
                img_resized = img.resize((new_w, new_h), PILImage.LANCZOS)
                buf = _io.BytesIO()
                img_resized.save(buf, format="PNG", optimize=True)
                return buf.getvalue(), w / new_w, h / new_h
        except Exception:  # noqa: BLE001 - resize must never break vision extraction.
            return image_bytes, 1.0, 1.0

    def _extract_page(self, provider_cascade: ProviderCascade, page: object, cfg: ProjectConfig) -> dict:
        img_path = Path(page.image.path)
        if not img_path.exists():
            return {"bubbles": [], "scene_summary": ""}

        image_bytes = img_path.read_bytes()
        resized_bytes, scale_x, scale_y = self._resize_and_get_scale(image_bytes)
        prompt = _build_vision_prompt()

        try:
            result, _candidate = provider_cascade.call_vision_structured(
                messages=[{"role": "user", "content": prompt}],
                images=[resized_bytes],
                schema={
                    "type": "object",
                    "properties": {
                        "bubbles": {"type": "array"},
                        "visual_footnotes": {"type": "array"},
                        "voice_hints": {"type": "array"},
                        "scene_summary": {"type": "string"},
                    },
                },
                operation="vision_structured",
                trace_context={"page_id": getattr(page, "page_id", "")},
            )
            result["_scale_x"] = scale_x
            result["_scale_y"] = scale_y
            return result
        except Exception:
            raw, _candidate = provider_cascade.call_vision(
                messages=[{"role": "user", "content": prompt}],
                images=[image_bytes],
                operation="vision_text_fallback",
                trace_context={"page_id": getattr(page, "page_id", "")},
            )
        return {"raw": raw, "bubbles": [], "scene_summary": ""}

    def _apply_to_page(self, page: object, result: dict) -> None:
        bubbles_raw = result.get("bubbles", [])
        page_width = int(getattr(getattr(page, "image", None), "width", 0) or 0)
        page_height = int(getattr(getattr(page, "image", None), "height", 0) or 0)
        # Apply the scale factors computed in _extract_page so that vision-model
        # bboxes — which were generated at the resized resolution — are mapped
        # back to the original page coordinate space.
        scale_x = float(result.get("_scale_x", 1.0))
        scale_y = float(result.get("_scale_y", 1.0))
        page_idx = getattr(page, "page_index", 0)
        vision_added = 0
        for b in bubbles_raw:
            # Adversarial validation: drop hallucinated bubbles (empty text,
            # zero/tiny bbox, far off-page) before they enter the pipeline.
            validated = self._validate_vision_bubble(b, page_width, page_height)
            if validated is None:
                continue
            bbox, source_text = validated

            # Scale bbox from vision-model resolution back to full page resolution.
            if scale_x != 1.0 or scale_y != 1.0:
                bbox = BoundingBox(
                    x=bbox.x * scale_x,
                    y=bbox.y * scale_y,
                    width=bbox.width * scale_x,
                    height=bbox.height * scale_y,
                )

            # Use the canonical vision- bubble_id prefix so the render stage's
            # _inject_vision_regions / _write_page_translations recognise these
            # bubbles (they only match region- and vision- prefixes).
            bubble_id = f"vision-{page_idx:04d}-{vision_added:04d}"

            page.bubbles.append(Bubble(
                bubble_id=bubble_id,
                bbox=bbox,
                source_text=source_text,
                reading_order=int(b.get("reading_order", vision_added)),
                speaker_id=b.get("speaker_id"),
                speaker_name=b.get("speaker_name"),
                tone=b.get("tone"),
                notes=b.get("notes"),
                box_type=b.get("box_type", "dialogue") or "dialogue",
                provisional_speaker=b.get("provisional_speaker") or b.get("speaker_name"),
                voice_hint=b.get("voice_hint"),
                vision_notes=b.get("vision_notes") or b.get("notes"),
                detection_source="vision",
                vision_confidence=b.get("confidence"),
            ))
            vision_added += 1
        self._apply_page_level_enrichment(page, result)
        page.scene_summary = result.get("scene_summary", "")

    @staticmethod
    def _extract_bbox_from_raw(raw: dict) -> BoundingBox:
        """Extract a BoundingBox from a raw LLM bubble dict.

        Tries ``bbox`` dict first (``{x, y, width, height}``), then falls
        back to ``lines`` (quadrilateral point arrays). Returns default
        ``BoundingBox()`` when no position data is available.
        """
        raw_bbox = raw.get("bbox")
        if raw_bbox and isinstance(raw_bbox, dict):
            try:
                bbox = BoundingBox(
                    x=float(raw_bbox.get("x", 0)),
                    y=float(raw_bbox.get("y", 0)),
                    width=float(raw_bbox.get("width", 0)),
                    height=float(raw_bbox.get("height", 0)),
                )
                if bbox.width > 0 and bbox.height > 0:
                    return bbox
            except (AttributeError, TypeError, ValueError):
                pass

        # Fallback: convert "lines" (quadrilateral point arrays) to bbox.
        lines = raw.get("lines")
        if lines:
            try:
                import numpy as np
                pts = np.array(lines).reshape(-1, 2)
                x_min, y_min = pts.min(axis=0)
                x_max, y_max = pts.max(axis=0)
                w = float(x_max - x_min)
                h = float(y_max - y_min)
                if w > 0 and h > 0:
                    return BoundingBox(
                        x=float(x_min), y=float(y_min),
                        width=w, height=h,
                    )
            except (ValueError, TypeError):
                pass

        return BoundingBox()

    # Minimum bbox area (px²) for an LLM-detected vision bubble. Below this the
    # box is almost always a hallucinated dot or a stray punctuation mark.
    _MIN_VISION_BUBBLE_AREA = 64.0
    # Allow a few px of bbox overflow past the image edge before dropping (LLM
    # coordinate rounding is imprecise); larger overflow is clamped to bounds.
    _BOUNDS_CLAMP_TOLERANCE = 2.0

    @classmethod
    def _validate_vision_bubble(
        cls,
        raw: dict,
        page_width: int,
        page_height: int,
        page_ocr_text: set[str] | None = None,
        *,
        current_page_id: str = "",
        all_pages_ocr: dict[str, set[str]] | None = None,
    ) -> tuple[BoundingBox, str] | None:
        """Adversarially validate a raw vision-LLM bubble.

        Returns ``(bbox, source_text)`` for accepted bubbles, or ``None`` for
        rejected ones (with a debug log of the reason). Guards against the most
        common vision-LLM hallucinations:

        * empty/garbage ``source_text``
        * missing or zero-area bbox (no usable geometry)
        * bbox far outside the page bounds
        * text with no OCR-level support on this page (bleed from another page)
        * cross-page context bleed (text that belongs to a different page)
        """
        source_text = str(raw.get("source_text", "")).strip()
        if not source_text:
            logger.debug("vision: dropping bubble with empty source_text")
            return None

        bbox = cls._extract_bbox_from_raw(raw)
        if bbox.width <= 0 or bbox.height <= 0:
            logger.debug(
                "vision: dropping bubble %r with non-positive bbox (%.0f, %.0f, %.0f, %.0f)",
                source_text[:20], bbox.x, bbox.y, bbox.width, bbox.height,
            )
            return None

        if bbox.width * bbox.height < cls._MIN_VISION_BUBBLE_AREA:
            logger.debug(
                "vision: dropping bubble %r with tiny area %.0f",
                source_text[:20], bbox.width * bbox.height,
            )
            return None

        # Clamp minor overflow to the page bounds; reject gross overflow.
        if page_width > 0 and page_height > 0:
            x_max = bbox.x + bbox.width
            y_max = bbox.y + bbox.height
            overflow_x = max(-bbox.x, x_max - page_width)
            overflow_y = max(-bbox.y, y_max - page_height)
            if overflow_x > cls._BOUNDS_CLAMP_TOLERANCE or overflow_y > cls._BOUNDS_CLAMP_TOLERANCE:
                # Clamp to bounds if the bulk of the box is inside, else drop.
                clamped_x = max(0.0, min(bbox.x, float(page_width)))
                clamped_y = max(0.0, min(bbox.y, float(page_height)))
                clamped_w = max(0.0, min(bbox.width, float(page_width) - clamped_x))
                clamped_h = max(0.0, min(bbox.height, float(page_height) - clamped_y))
                if clamped_w * clamped_h < cls._MIN_VISION_BUBBLE_AREA:
                    logger.debug(
                        "vision: dropping bubble %r off-page "
                        "(bbox=(%.0f,%.0f,%.0f,%.0f) page=%dx%d)",
                        source_text[:20], bbox.x, bbox.y, bbox.width, bbox.height,
                        page_width, page_height,
                    )
                    return None
                bbox = BoundingBox(
                    x=clamped_x, y=clamped_y, width=clamped_w, height=clamped_h,
                )

        # Hallucination guard: long sentence with no OCR-level textual support
        # on this page is likely a bleed from another page.
        if page_ocr_text and len(source_text) > 10:
            cleaned = source_text.strip()
            if not any(
                _text_overlap(cleaned, ocr_line) >= 0.2
                for ocr_line in page_ocr_text
            ):
                logger.debug(
                    "vision: hallucination guard rejected bubble %r "
                    "(no OCR-level textual overlap on this page)",
                    source_text[:30],
                )
                return None

        # Cross-page bleed guard: reject text that has stronger phrase-level
        # overlap with a different page than the current one.
        if all_pages_ocr and current_page_id and len(source_text) > 10:
            bleed_from = _cross_page_bleed_check(
                source_text,
                current_page_id,
                page_ocr_text or set(),
                all_pages_ocr,
            )
            if bleed_from is not None:
                logger.warning(
                    "vision: cross-page bleed — bubble %r belongs to %s, "
                    "not %s (rejecting)",
                    source_text[:30],
                    bleed_from,
                    current_page_id,
                )
                return None

        return bbox, source_text

    def _apply_enrichment_to_page(
        self,
        page: object,
        result: dict,
        *,
        all_pages_ocr: dict[str, set[str]] | None = None,
    ) -> None:
        by_id = {bubble.bubble_id: bubble for bubble in page.bubbles}
        by_order: dict[int, Bubble] = {}
        for bubble in page.bubbles:
            if bubble.reading_order in by_order:
                logger.warning(
                    f"reading_order collision on page {getattr(page, 'page_index', '?')}: "
                    f"{bubble.bubble_id} and {by_order[bubble.reading_order].bubble_id} "
                    f"both have reading_order={bubble.reading_order} — last-writer wins"
                )
            by_order[bubble.reading_order] = bubble
        for i, raw in enumerate(result.get("bubbles", [])):
            bubble = self._match_enrichment_bubble(raw, by_id, by_order, i)
            if bubble is None:
                continue
            # OCR remains authoritative for source_text and bbox.
            bubble.box_type = raw.get("box_type") or bubble.box_type
            bubble.provisional_speaker = raw.get("provisional_speaker") or bubble.provisional_speaker
            bubble.voice_hint = raw.get("voice_hint") or bubble.voice_hint
            bubble.vision_notes = raw.get("vision_notes") or raw.get("notes") or bubble.vision_notes
            bubble.tone = raw.get("tone") or bubble.tone
            bubble.notes = raw.get("notes") or bubble.notes

        matched_indices = set()
        for i, raw in enumerate(result.get("bubbles", [])):
            bubble = self._match_enrichment_bubble(raw, by_id, by_order, i)
            if bubble is not None:
                matched_indices.add(i)

        vision_added = 0
        page_width = int(getattr(getattr(page, "image", None), "width", 0) or 0)
        page_height = int(getattr(getattr(page, "image", None), "height", 0) or 0)
        scale_x = float(result.get("_scale_x", 1.0))
        scale_y = float(result.get("_scale_y", 1.0))

        # Collect OCR text on this page for cross-page hallucination guard.
        page_ocr_text = {
            bubble.source_text
            for bubble in page.bubbles
            if bubble.source_text and bubble.detection_source != "vision"
        }
        for i, raw in enumerate(result.get("bubbles", [])):
            if i in matched_indices:
                continue

            # Shared adversarial validator: bbox extraction + bounds + area +
            # non-empty source_text + cross-page bleed detection. Drops
            # hallucinated bubbles consistently.
            page_id = getattr(page, "page_id", "")
            validated = self._validate_vision_bubble(
                raw, page_width, page_height, page_ocr_text,
                current_page_id=page_id,
                all_pages_ocr=all_pages_ocr,
            )
            if validated is None:
                continue
            vision_bbox, source_text = validated

            # Scale bbox from vision-model resolution back to full page resolution.
            if scale_x != 1.0 or scale_y != 1.0:
                vision_bbox = BoundingBox(
                    x=vision_bbox.x * scale_x,
                    y=vision_bbox.y * scale_y,
                    width=vision_bbox.width * scale_x,
                    height=vision_bbox.height * scale_y,
                )

            # Shrink vision bbox by 2% of page dimension on each side to prevent
            # overlap with adjacent regions (vision models return loose bboxes).
            if page_width > 0 and page_height > 0:
                margin_x = max(1, int(page_width * 0.02))
                margin_y = max(1, int(page_height * 0.02))
                shrunk_w = max(10, vision_bbox.width - 2 * margin_x)
                shrunk_h = max(10, vision_bbox.height - 2 * margin_y)
                vision_bbox = BoundingBox(
                    x=max(0, vision_bbox.x + margin_x),
                    y=max(0, vision_bbox.y + margin_y),
                    width=shrunk_w,
                    height=shrunk_h,
                )

            # Skip bubbles that largely overlap an existing OCR region.
            max_iou = 0.0
            for existing in page.bubbles:
                if existing.bbox and existing.bbox.width > 0 and existing.bbox.height > 0:
                    iou = _compute_iou(vision_bbox, existing.bbox)
                    max_iou = max(max_iou, iou)
            if max_iou > 0.3:
                continue

            page_idx = getattr(page, "page_index", 0)
            new_bubble = Bubble(
                bubble_id=f"vision-{page_idx:04d}-{vision_added:04d}",
                bbox=vision_bbox,
                source_text=source_text,
                reading_order=len(page.bubbles),
                detection_source="vision",
                vision_confidence=raw.get("confidence"),
                box_type=raw.get("box_type", "dialogue") or "dialogue",
                provisional_speaker=raw.get("provisional_speaker"),
                voice_hint=raw.get("voice_hint"),
                tone=raw.get("tone"),
                notes=raw.get("notes"),
            )
            page.bubbles.append(new_bubble)
            vision_added += 1

        supplemented = getattr(page, "_vision_supplemented", 0) + vision_added
        try:
            page._vision_supplemented = supplemented
        except ValueError:
            object.__setattr__(page, "_vision_supplemented", supplemented)

        self._apply_page_level_enrichment(page, result)
        if result.get("scene_summary"):
            page.scene_summary = result["scene_summary"]

    def _match_enrichment_bubble(
        self,
        raw: dict,
        by_id: dict[str, Bubble],
        by_order: dict[int, Bubble],
        fallback_order: int,
    ) -> Bubble | None:
        raw_id = str(raw.get("bubble_id", ""))
        if raw_id in by_id:
            return by_id[raw_id]
        try:
            order = int(raw.get("reading_order", fallback_order))
        except (TypeError, ValueError):
            order = fallback_order
        return by_order.get(order)

    def _apply_page_level_enrichment(self, page: object, result: dict) -> None:
        existing_footnotes = list(getattr(page, "visual_footnotes", []) or [])
        new_footnotes = [
            self._make_visual_footnote(item)
            for item in result.get("visual_footnotes", [])
            if isinstance(item, dict)
        ]
        seen_footnotes = {self._visual_footnote_key(item) for item in existing_footnotes}
        for footnote in new_footnotes:
            key = self._visual_footnote_key(footnote)
            if key in seen_footnotes:
                continue
            existing_footnotes.append(footnote)
            seen_footnotes.add(key)
        page.visual_footnotes = existing_footnotes

        existing_hints = list(getattr(page, "voice_hints", []) or [])
        seen_hints = {str(hint).strip() for hint in existing_hints if str(hint).strip()}
        hints = result.get("voice_hints", [])
        for hint in hints:
            text = str(hint)
            key = text.strip()
            if not key or key in seen_hints:
                continue
            existing_hints.append(text)
            seen_hints.add(key)
        page.voice_hints = existing_hints

    def _visual_footnote_key(self, footnote: VisualFootnote) -> tuple:
        bbox = footnote.bbox
        bbox_key = None
        if bbox is not None:
            bbox_key = (bbox.x, bbox.y, bbox.width, bbox.height)
        return (
            footnote.source_text,
            footnote.translation_hint,
            footnote.kind,
            bbox_key,
            footnote.notes,
        )

    def _make_visual_footnote(self, raw: dict) -> VisualFootnote:
        return VisualFootnote(
            source_text=str(raw.get("source_text", "")),
            translation_hint=str(raw.get("translation_hint", "")),
            kind=str(raw.get("kind", "other") or "other"),
            bbox=self._parse_visual_footnote_bbox(raw.get("bbox")),
            notes=raw.get("notes"),
        )

    def _parse_visual_footnote_bbox(self, bbox: object) -> BoundingBox | None:
        try:
            if isinstance(bbox, dict):
                return BoundingBox(
                    x=float(bbox.get("x", 0.0)),
                    y=float(bbox.get("y", 0.0)),
                    width=float(bbox.get("width", 0.0)),
                    height=float(bbox.get("height", 0.0)),
                )
            if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                x, y, width, height = bbox
                return BoundingBox(
                    x=float(x),
                    y=float(y),
                    width=float(width),
                    height=float(height),
                )
        except (TypeError, ValueError):
            return None
        return None


VisionStage = VisionEnrichmentStage
