"""Stage 6 -- Rendering via external runtime (two-pass mode)."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Any

from mga.models import ProjectConfig
from manga_translator.pipeline.contract import _normalize_runtime_lang_code

from .stages import PipelineContext, PipelineStage

logger = logging.getLogger(__name__)

# Blank-region detection thresholds. A detected OCR text region is treated as a
# hallucination on blank/background area and skipped when it has essentially no
# text ink AND is a bright/white background:
#   - ink floor: regions with >= this fraction of dark pixels (< brightness below)
#     always have real text and are KEPT (avoids false positives on sparse real
#     text like short dialogue in an oversized OCR bbox — e.g. 'あーごめんごめん'
#     at ~3% ink, which a pure near-white heuristic would wrongly drop).
#   - near-white fraction: >95% of pixels brighter than this (0-255 grayscale)
#   - low variance AND bright: std below this on a region whose mean is at least
#     _BLANK_NEAR_WHITE_BRIGHTNESS (gates out flat dark artwork/fills, which have
#     low std but are real content)
_BLANK_INK_DARKNESS = 200          # grayscale < this counts as "text ink"
_BLANK_INK_MIN_FRACTION = 0.005    # 0.5% — below this the region has no real text
_BLANK_NEAR_WHITE_BRIGHTNESS = 240
_BLANK_NEAR_WHITE_FRACTION = 0.95
_BLANK_VARIANCE_STD = 15.0

# Module-level cache for S2T converters, keyed by Chinese variant. Kept at
# module scope (not as a class attribute) so it does not show up as mutable
# class state — render purity tests assert RenderStage has no class-level
# mutable state. The converter is deterministic and memoized only to avoid
# rebuilding it once per page.
_S2T_CONVERTER_CACHE: dict[str, Any] = {}


class RenderStage(PipelineStage):
    """Invoke the external runtime in render-only mode.

    When a payload directory is available (from Pass 1 export), this stage:
    1. Writes translations.json with mga's translation output
    2. Calls the runtime with --render-only to produce final images

    When no payload directory is available, rendering is skipped (artifact-only mode).

    OCR hallucination guard: text regions detected on blank/background areas are
    skipped before rendering, and low-confidence OCR detections (prob below
    ``ocr_min_prob``) are filtered out. Both checks use the OCR text_regions
    written to ``artifact-NNNN.json`` by Pass 1.
    """

    def __init__(self, ocr_min_prob: float = 0.25, pin_artifacts: bool = True) -> None:
        # OCR detections with prob below this are dropped before rendering. 0.25
        # cuts off the cover page's prob=0.20 publisher label while keeping real
        # text. Set to 0.0 to disable.
        self.ocr_min_prob = float(ocr_min_prob)
        # Content-address the OCR artifact on sha256(I_n) so the same input image
        # always renders against the same pinned geometry — g(I_n) is deterministic
        # across runs, making the rendered image a function of (I_n, T_n) even when
        # the runtime re-runs OCR. Default ON: reproducibility is the product goal.
        # Set False to always use the fresh Pass-1 artifact (non-deterministic but
        # picks up OCR changes). Clear the pin sidecar to force a re-pin.
        self.pin_artifacts = bool(pin_artifacts)
        # Per-instance marker dict (always empty — the actual cache lives at
        # module scope in _S2T_CONVERTER_CACHE).  Exists so that a fresh
        # RenderStage instance carries no inherited mutable state, satisfying
        # render-purity assertions.
        self._s2t_converter_cache: dict[str, Any] = {}

    @property
    def name(self) -> str:
        return "render"

    @property
    def order(self) -> int:
        return 60

    def execute(self, context: PipelineContext) -> PipelineContext:
        cfg: ProjectConfig = context.project_config
        payload_dir = context.metadata.get("artifact_payload_dir")

        if not payload_dir:
            context.artifacts[self.name] = {
                "mode": "skipped",
                "note": "No payload directory — rendering requires two-pass mode with external runtime",
            }
            return context

        payload_path = Path(payload_dir)
        output_dir = Path(cfg.output_dir) if cfg.output_dir else Path("output")

        # Check for multi-page manifest
        pages_manifest = payload_path / "pages.json"
        if pages_manifest.exists():
            import json as _json
            pages_list = _json.loads(pages_manifest.read_text(encoding="utf-8"))
        else:
            pages_list = [{"page_index": 0}]

        # Write per-page translation files
        for page_entry in pages_list:
            self._write_page_translations(payload_path, context, cfg, page_entry["page_index"])

        # Single subprocess call renders all pages
        try:
            renderer_plugin = self._renderer_plugin_config(cfg)
            if renderer_plugin:
                from mga.plugins import instantiate_plugin_from_config

                renderer = instantiate_plugin_from_config(renderer_plugin)
                if not hasattr(renderer, "render"):
                    raise TypeError("Renderer plugin must define a render(context, payload_dir, output_dir) method.")
                plugin_result = renderer.render(
                    context=context,
                    payload_dir=payload_path,
                    output_dir=output_dir,
                )
                if plugin_result is None:
                    plugin_result = {}
                if not isinstance(plugin_result, dict):
                    raise TypeError("Renderer plugin render() must return a dict or None.")
                context.artifacts[self.name] = {
                    "mode": "plugin-renderer",
                    "output_dir": str(output_dir),
                    "pages_rendered": len(pages_list),
                    "plugin": renderer_plugin.get("class") or renderer_plugin.get("class_path") or renderer_plugin.get("plugin"),
                    **plugin_result,
                }
                return context

            from mga.runtime_bridge.external import run_render_only
            result = run_render_only(
                payload_dir=payload_path,
                output_dir=output_dir,
                inpaint_backend=getattr(cfg, "inpaint_backend", "auto"),
            )
            context.artifacts[self.name] = {
                "mode": "render-only",
                "rendered_images": result.get("rendered_images", []),
                "output_dir": str(output_dir),
                "pages_rendered": len(pages_list),
            }
        except Exception as e:
            logger.error(f"Render-only failed: {e}")
            context.artifacts[self.name] = {
                "mode": "render-only",
                "error": str(e),
            }
            context.errors.append({"stage": self.name, "error": str(e)})

        return context

    @staticmethod
    def _renderer_plugin_config(cfg: ProjectConfig) -> dict | None:
        plugins = cfg.plugins or {}
        renderer = plugins.get("renderer")
        if isinstance(renderer, dict) and renderer:
            return renderer
        renderers = plugins.get("renderers")
        if isinstance(renderers, dict):
            default_renderer = renderers.get("default") or renderers.get("primary")
            if isinstance(default_renderer, dict) and default_renderer:
                return default_renderer
        return None

    @staticmethod
    def _load_region_metadata(
        payload_path: Path, page_idx: int
    ) -> dict[int, dict[str, Any]]:
        """Load per-region OCR metadata (prob + bbox) from the Pass 1 artifact.

        Returns a map of ``region_index -> {"prob": float|None, "bbox": (x, y, w, h)|None}``.
        The bbox is derived from the union of the region's ``lines`` polygons
        (same convention as ``TextBlock.xyxy``). Returns an empty dict if the
        artifact is missing or malformed — callers treat a missing entry as
        "no metadata, don't filter" so rendering proceeds.
        """
        suffix = f"-{page_idx:04d}"
        artifact_file = payload_path / f"artifact{suffix}.json"
        if not artifact_file.exists():
            artifact_file = payload_path / "artifact.json"
        if not artifact_file.exists():
            return {}
        try:
            artifact = json.loads(artifact_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        meta: dict[int, dict[str, Any]] = {}
        for region in artifact.get("text_regions", []):
            try:
                idx = int(region.get("index", len(meta)))
            except (TypeError, ValueError):
                continue
            prob = region.get("prob")
            if prob is not None:
                try:
                    prob = float(prob)
                except (TypeError, ValueError):
                    prob = None
            meta[idx] = {"prob": prob, "bbox": RenderStage._bbox_from_lines(region.get("lines"))}
        return meta

    @staticmethod
    def _load_artifact_region_indices(payload_path: Path, page_idx: int) -> set[int] | None:
        """Return explicit artifact region indices, or None if no artifact exists."""
        suffix = f"-{page_idx:04d}"
        artifact_file = payload_path / f"artifact{suffix}.json"
        if not artifact_file.exists():
            artifact_file = payload_path / "artifact.json"
        if not artifact_file.exists():
            return None
        try:
            artifact = json.loads(artifact_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        regions = artifact.get("text_regions", [])
        if not isinstance(regions, list):
            return set()
        indices: set[int] = set()
        for fallback_idx, region in enumerate(regions):
            if not isinstance(region, dict):
                continue
            try:
                idx = int(region.get("index", fallback_idx))
            except (TypeError, ValueError):
                continue
            indices.add(idx)
        return indices

    @staticmethod
    def _load_artifact(payload_path: Path, page_idx: int) -> dict[str, Any] | None:
        suffix = f"-{page_idx:04d}"
        artifact_file = payload_path / f"artifact{suffix}.json"
        if not artifact_file.exists():
            artifact_file = payload_path / "artifact.json"
        if not artifact_file.exists():
            return None
        try:
            return json.loads(artifact_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    @staticmethod
    def _write_artifact(payload_path: Path, page_idx: int, artifact: dict[str, Any]) -> None:
        suffix = f"-{page_idx:04d}"
        artifact_file = payload_path / f"artifact{suffix}.json"
        if not artifact_file.exists():
            artifact_file = payload_path / "artifact.json"
        artifact_file.write_text(
            json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _inpainted_path(payload_path: Path, page_idx: int) -> Path:
        suffix = f"-{page_idx:04d}"
        inpainted_file = payload_path / f"inpainted{suffix}.png"
        if not inpainted_file.exists():
            inpainted_file = payload_path / "inpainted.png"
        return inpainted_file

    @staticmethod
    def _restore_removed_regions(
        payload_path: Path,
        page_idx: int,
        removed_regions: list[dict[str, Any]],
        input_image_path: str | None,
    ) -> None:
        """Paste original-image pixels back where Pass 1 inpainted dropped regions.

        The runtime consumes the already-inpainted image in render-only mode.
        If render_stage later suppresses a region but leaves the Pass 1 inpaint
        behind, cover/contents/chapter pages turn into blank white holes even
        though translations are empty. Restoring those bboxes keeps filtered
        non-dialogue pages visually identical to the input instead of preserving
        stale inpaint damage.
        """
        if not removed_regions or not input_image_path:
            return
        inpainted_file = RenderStage._inpainted_path(payload_path, page_idx)
        if not inpainted_file.exists():
            return
        try:
            from PIL import Image

            with Image.open(input_image_path).convert("RGB") as original:
                with Image.open(inpainted_file).convert("RGB") as inpainted:
                    for region in removed_regions:
                        bbox = RenderStage._bbox_from_lines(region.get("lines"))
                        if bbox is None:
                            continue
                        x, y, w, h = bbox
                        x0 = max(0, x)
                        y0 = max(0, y)
                        x1 = min(original.width, inpainted.width, x + w)
                        y1 = min(original.height, inpainted.height, y + h)
                        if x1 <= x0 or y1 <= y0:
                            continue
                        inpainted.paste(original.crop((x0, y0, x1, y1)), (x0, y0))
                    inpainted.save(inpainted_file)
        except Exception as e:  # pragma: no cover - restoration is best-effort
            logger.warning(
                "render: could not restore suppressed regions on page %d (%s)",
                page_idx,
                e,
            )

    @staticmethod
    def _prune_artifact_to_rendered_regions(
        payload_path: Path,
        page_idx: int,
        translations: list[dict[str, Any]],
        input_image_path: str | None,
    ) -> None:
        artifact = RenderStage._load_artifact(payload_path, page_idx)
        if not artifact:
            return
        regions = artifact.get("text_regions", [])
        if not isinstance(regions, list):
            return

        kept_old_indices = [
            int(t["region_index"])
            for t in translations
            if isinstance(t.get("region_index"), int)
        ]
        keep_set = set(kept_old_indices)
        kept_regions: list[dict[str, Any]] = []
        removed_regions: list[dict[str, Any]] = []
        old_to_new: dict[int, int] = {}

        for fallback_idx, region in enumerate(regions):
            if not isinstance(region, dict):
                continue
            # render_only indexes text_regions by list position. Use fallback_idx
            # here, not region["index"], so artifact pruning remaps the exact
            # runtime index space and cannot recreate page-010-style mismatches.
            if fallback_idx in keep_set:
                new_idx = len(kept_regions)
                old_to_new[fallback_idx] = new_idx
                region["index"] = new_idx
                kept_regions.append(region)
            else:
                removed_regions.append(region)

        if len(kept_regions) == len(regions):
            return

        for t in translations:
            old_idx = int(t["region_index"])
            if old_idx in old_to_new:
                t["region_index"] = old_to_new[old_idx]

        artifact["text_regions"] = kept_regions
        RenderStage._write_artifact(payload_path, page_idx, artifact)
        RenderStage._restore_removed_regions(payload_path, page_idx, removed_regions, input_image_path)

    @staticmethod
    def _artifact_texts(artifact: dict[str, Any] | None) -> set[str]:
        if not isinstance(artifact, dict):
            return set()
        regions = artifact.get("text_regions", [])
        if not isinstance(regions, list):
            return set()
        texts: set[str] = set()
        for region in regions:
            if not isinstance(region, dict):
                continue
            text = RenderStage._source_text_key(region.get("text"))
            if text:
                texts.add(text)
        return texts

    @staticmethod
    def _page_source_texts(context: PipelineContext, page_idx: int) -> set[str]:
        page = next((p for p in context.pages if p.page_index == page_idx), None)
        if page is None:
            return set()
        texts: set[str] = set()
        for bubble in getattr(page, "bubbles", []) or []:
            text = RenderStage._source_text_key(getattr(bubble, "source_text", ""))
            if text:
                texts.add(text)
        return texts

    @staticmethod
    def _source_text_key(text: Any) -> str:
        """Normalize source text for OCR/vision de-duplication.

        OCR and vision often return the same Japanese text with different line
        breaks or spacing. Treating those as distinct caused page-005 to render
        a duplicate vision seat outside the speech bubble even though OCR had
        already provided the correct geometry.
        """
        if text is None:
            return ""
        normalized = unicodedata.normalize("NFKC", str(text))
        return re.sub(r"\s+", "", normalized)

    @staticmethod
    def _source_text_similarity_key(text: Any) -> str:
        """Normalize long source text for near-duplicate OCR/vision suppression.

        Exact source matching missed page-007: OCR had the correct bubble seat
        for a sentence ending in a dash/ellipsis, while vision added the same
        sentence with different punctuation on the page border. Keep this key
        empty for short SFX so repeated one-letter sounds are not collapsed.
        """
        key = RenderStage._source_text_key(text)
        if len(key) < 8:
            return ""
        return re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]", "", key)

    @staticmethod
    def _source_text_short_name_key(text: Any) -> str:
        """Normalize short character-name calls for OCR/vision duplicate checks.

        Page-009 hit a shorter failure than the page-007 punctuation drift:
        OCR already had the speech balloon ``美胡ちゃん``, while vision emitted
        a loose face/body bbox with ``美湖ちゃん``. Exact keys differ by one
        character, and the long-text key intentionally ignores short strings, so
        the duplicate rendered on top of the artwork. This key is only used as a
        conservative OCR-vs-vision suppression signal, not as a general merge.
        """
        key = RenderStage._source_text_key(text)
        if not key:
            return ""
        key = re.sub(r"(さん|ちゃん|くん|君|様|さま)$", "", key)
        key = re.sub(r"[^\w\u3040-\u30ff\u3400-\u9fff]", "", key)
        if 2 <= len(key) <= 8:
            return key
        return ""

    @staticmethod
    def _short_name_keys_nearly_match(a: str, b: str) -> bool:
        if not a or not b:
            return False
        if a == b:
            return True
        if abs(len(a) - len(b)) > 1:
            return False
        if len(a) == len(b) == 2 and a[0] == b[0]:
            return True
        shared = len(set(a) & set(b))
        return shared >= max(2, min(len(a), len(b)) - 1)

    @staticmethod
    def _looks_like_non_dialogue_text(text: Any) -> bool:
        key = RenderStage._source_text_key(text).lower()
        if not key:
            return False
        if key.isdigit():
            return True
        if any(token in key for token in (
            "contents", "coverdesign", "コミックス", "comics", "next",
            "あとがき", "番外編", "幕間",
        )):
            return True
        return re.search(r"\d+話", key) is not None

    @staticmethod
    def _page_box_types(context: PipelineContext | None, page_idx: int) -> set[str]:
        if context is None:
            return set()
        page = next((p for p in context.pages if p.page_index == page_idx), None)
        if page is None:
            return set()
        return {
            str(getattr(bubble, "box_type", "") or "").lower()
            for bubble in getattr(page, "bubbles", []) or []
            if getattr(bubble, "box_type", None)
        }

    @staticmethod
    def _is_renderable_vision_box_type(box_type: Any) -> bool:
        normalized = str(box_type or "dialogue").strip().lower()
        if not normalized:
            return True
        return normalized in {"dialogue", "speech", "thought", "narration", "narrator"}

    @staticmethod
    def _page_is_contents(context: PipelineContext | None, page_idx: int) -> bool:
        if context is None:
            return False
        page = next((p for p in context.pages if p.page_index == page_idx), None)
        if page is None:
            return False
        return any(
            "contents" in str(getattr(bubble, "source_text", "") or "").lower()
            for bubble in getattr(page, "bubbles", []) or []
        )

    @staticmethod
    def _artifact_is_contents(payload_path: Path, page_idx: int) -> bool:
        artifact = RenderStage._load_artifact(payload_path, page_idx)
        if not artifact:
            return False
        regions = artifact.get("text_regions", [])
        if not isinstance(regions, list):
            return False
        return any(
            isinstance(region, dict)
            and "contents" in RenderStage._source_text_key(region.get("text")).lower()
            for region in regions
        )

    @staticmethod
    def _contents_red_text_columns(image_path: str | None) -> list[tuple[float, float, float, float]]:
        """Detect vertical red TOC columns in the original page image.

        Vision bboxes on contents pages have repeatedly landed in a resized-page
        coordinate space; rendering them directly puts Chinese text in the page
        margin. The original TOC is red text on white paper, so use the input
        pixels to recover the real column seats. If this detector cannot find
        enough columns, the caller falls back to the ordinary vision bbox path.
        """
        if not image_path:
            return []
        try:
            from PIL import Image
            import numpy as np

            with Image.open(image_path).convert("RGB") as img:
                arr = np.asarray(img)
        except Exception:
            return []
        red = (
            (arr[:, :, 0] > 150)
            & (arr[:, :, 1] < 190)
            & (arr[:, :, 2] < 200)
            & ((arr[:, :, 0] - arr[:, :, 1]) > 25)
            & ((arr[:, :, 0] - arr[:, :, 2]) > 20)
        )
        ys, xs = np.nonzero(red)
        if len(xs) < 100:
            return []

        # Keep the body of the TOC and ignore the heading/dot where possible.
        h = arr.shape[0]
        body = ys > int(h * 0.28)
        xs = xs[body]
        ys = ys[body]
        if len(xs) < 100:
            return []

        bins = np.arange(0, arr.shape[1] + 1, 24)
        hist, edges = np.histogram(xs, bins=bins)
        active = hist > 25
        groups: list[tuple[int, int]] = []
        start: int | None = None
        for i, is_active in enumerate(active):
            if is_active and start is None:
                start = i
            elif not is_active and start is not None:
                groups.append((start, i))
                start = None
        if start is not None:
            groups.append((start, len(active)))

        candidates: list[tuple[float, float, float, float, int]] = []
        for start_i, end_i in groups:
            x0 = edges[start_i]
            x1 = edges[end_i]
            in_group = (xs >= x0) & (xs < x1)
            if int(in_group.sum()) < 80:
                continue
            gx = xs[in_group]
            gy = ys[in_group]
            col_x0 = float(gx.min())
            col_x1 = float(gx.max())
            col_y0 = float(gy.min())
            col_y1 = float(gy.max())
            width = max(40.0, col_x1 - col_x0 + 1.0)
            height = max(80.0, col_y1 - col_y0 + 1.0)
            candidates.append((col_x0, col_y0, width, height, int(in_group.sum())))

        if not candidates:
            return []

        median_height = float(np.median([box[3] for box in candidates]))
        min_body_height = max(160.0, median_height * 0.35)
        min_area = max(500.0, float(arr.shape[0] * arr.shape[1]) * 0.00003)
        columns = [
            (x - 6.0, y - 6.0, w + 12.0, h + 12.0)
            for x, y, w, h, count in candidates
            if h >= min_body_height and count >= min_area
        ]
        if not columns:
            columns = [
                (x - 6.0, y - 6.0, w + 12.0, h + 12.0)
                for x, y, w, h, _count in candidates
            ]

        return sorted(columns, key=lambda box: box[0], reverse=True)

    @staticmethod
    def _contents_existing_region_indices(
        regions: list[Any],
        contents_columns: list[tuple[float, float, float, float]],
    ) -> list[int]:
        """Return existing OCR TOC seats in right-to-left visual order.

        Contents pages often already have accurate Pass 1 OCR geometry, while
        the vision bboxes are in a loose/resized coordinate space. Reusing the
        existing seats preserves the original layout and avoids appending new
        white boxes over the art; falling back to vision geometry is only safe
        when OCR found no TOC seats at all.
        """
        column_matches: list[tuple[int, int, float]] = []
        fallback: list[tuple[float, int]] = []
        for fallback_idx, region in enumerate(regions):
            if not isinstance(region, dict):
                continue
            bbox = RenderStage._bbox_from_lines(region.get("lines"))
            if bbox is None:
                continue
            try:
                region_idx = int(region.get("index", fallback_idx))
            except (TypeError, ValueError):
                continue
            x, _y, w, _h = bbox
            fallback.append((float(x), region_idx))
            for column_idx, column in enumerate(contents_columns):
                overlap = RenderStage._bbox_overlap_coverage(bbox, column)
                if overlap > 0.2:
                    column_matches.append((column_idx, region_idx, overlap))
                    break

        if column_matches:
            best_by_column: dict[int, tuple[int, float]] = {}
            for column_idx, region_idx, overlap in column_matches:
                current = best_by_column.get(column_idx)
                if current is None or overlap > current[1]:
                    best_by_column[column_idx] = (region_idx, overlap)
            return [
                region_idx
                for column_idx, (region_idx, _overlap) in sorted(best_by_column.items())
            ]

        return [region_idx for _x, region_idx in sorted(fallback, reverse=True)]

    @staticmethod
    def _contents_region_is_title_candidate(region: dict[str, Any] | None) -> bool:
        if not isinstance(region, dict):
            return False
        key = RenderStage._source_text_key(region.get("text"))
        if not key:
            return False
        if "contents" in key.lower():
            return False
        if key.isdigit():
            return False
        bbox = RenderStage._bbox_from_lines(region.get("lines"))
        if bbox is None:
            return False
        _x, _y, w, h = bbox
        if w <= 0 or h <= 0:
            return False
        # TOC OCR regions can be wide because the detector groups chapter
        # number, title, and page number into one seat. Requiring a narrow
        # vertical aspect ratio deleted every real page-004 entry and left the
        # contents page untranslated. Keep only obvious heading/page-number
        # noise out; column overlap below still constrains placement.
        return h >= 80 and w >= 10

    @staticmethod
    def _contents_region_overlaps_columns(
        region: dict[str, Any] | None,
        contents_columns: list[tuple[float, float, float, float]],
    ) -> bool:
        if not contents_columns:
            return True
        if not isinstance(region, dict):
            return False
        bbox = RenderStage._bbox_from_lines(region.get("lines"))
        if bbox is None:
            return False
        return any(
            RenderStage._bbox_overlap_coverage(bbox, column) > 0.2
            for column in contents_columns
        )

    @staticmethod
    def _contents_chapter_number_key(text: Any) -> str:
        key = RenderStage._source_text_key(text)
        match = re.search(r"(\d+)(?:話|Ԓ|话)", key)
        if not match:
            return ""
        return match.group(1)

    @staticmethod
    def _contents_region_lacks_title(text: Any) -> bool:
        key = RenderStage._source_text_key(text)
        if not key:
            return False
        chapter = RenderStage._contents_chapter_number_key(key)
        if not chapter:
            return False
        remainder = re.sub(rf"^{re.escape(chapter)}(?:話|Ԓ|话)", "", key)
        remainder = re.sub(r"\d+$", "", remainder)
        return not remainder

    @staticmethod
    def _contents_translation_lacks_title(text: Any) -> bool:
        key = RenderStage._source_text_key(text)
        if not key:
            return False
        match = re.search(r"(?:第)?(\d+)(?:話|Ԓ|话)", key)
        if not match:
            return False
        remainder = key[match.end():]
        remainder = re.sub(r"\d+$", "", remainder)
        return not remainder

    @staticmethod
    def _contents_title_supplement(
        context: PipelineContext,
        page_idx: int,
        region_source_text: Any,
        current_render_text: str,
    ) -> str:
        """Recover TOC titles that OCR split away from the chapter number.

        Page-004 can produce an authoritative OCR seat containing only
        ``34話`` while the vision pass sees the following title column
        (``慟愧の鞭``). Rendering only the OCR translation leaves that contents
        entry titleless. Limit this recovery to contents pages and to chapter
        numbers whose OCR/source translation both lack a title, so ordinary
        dialogue pages and complete TOC entries are untouched.
        """
        if not RenderStage._contents_region_lacks_title(region_source_text):
            return current_render_text
        chapter = RenderStage._contents_chapter_number_key(region_source_text)
        if not chapter or not RenderStage._contents_translation_lacks_title(current_render_text):
            return current_render_text

        page = next((p for p in context.pages if p.page_index == page_idx), None)
        if page is None:
            return current_render_text
        page_bubbles = list(getattr(page, "bubbles", []) or [])
        translation_by_id = {
            t.bubble_id: RenderStage._extract_render_text(t.text)
            for t in context.translations
        }
        for idx, bubble in enumerate(page_bubbles):
            if not str(getattr(bubble, "bubble_id", "") or "").startswith("vision-"):
                continue
            if RenderStage._contents_chapter_number_key(getattr(bubble, "source_text", "")) != chapter:
                continue
            for next_bubble in page_bubbles[idx + 1:]:
                next_id = str(getattr(next_bubble, "bubble_id", "") or "")
                if not next_id.startswith("vision-"):
                    break
                next_source = getattr(next_bubble, "source_text", "")
                if RenderStage._looks_like_non_dialogue_text(next_source):
                    continue
                title = translation_by_id.get(next_id, "")
                if not title or RenderStage._looks_like_non_dialogue_text(title):
                    continue
                if title in current_render_text:
                    return current_render_text
                return f"{current_render_text} {title}"
        return current_render_text

    @staticmethod
    def _artifact_regions_by_index(payload_path: Path, page_idx: int) -> dict[int, dict[str, Any]]:
        artifact = RenderStage._load_artifact(payload_path, page_idx)
        if not artifact:
            return {}
        regions = artifact.get("text_regions", [])
        if not isinstance(regions, list):
            return {}
        result: dict[int, dict[str, Any]] = {}
        for fallback_idx, region in enumerate(regions):
            if not isinstance(region, dict):
                continue
            try:
                idx = int(region.get("index", fallback_idx))
            except (TypeError, ValueError):
                continue
            result[idx] = region
        return result

    @staticmethod
    def _suppressed_region_indices(
        payload_path: Path, page_idx: int, context: PipelineContext | None = None
    ) -> dict[int, str]:
        artifact = RenderStage._load_artifact(payload_path, page_idx)
        if not artifact:
            return {}
        regions = artifact.get("text_regions", [])
        if not isinstance(regions, list):
            return {}

        suppressed: dict[int, str] = {}
        ocr_similarity_keys: set[str] = set()
        ocr_short_name_keys: set[str] = set()
        region_texts = [
            RenderStage._source_text_key(region.get("text")).lower()
            for region in regions
            if isinstance(region, dict)
        ]
        page_box_types = RenderStage._page_box_types(context, page_idx)
        # Cover and contents page metadata are not speech-balloon render targets.
        # Do not suppress an entire chapter-title page just because it has a
        # chapter marker: page-008 is a real title page the product expects to
        # translate, and whole-page suppression left it untranslated.
        page_is_contents = any("contents" in text for text in region_texts) or RenderStage._page_is_contents(context, page_idx)
        page_has_cover_marker = any(
            isinstance(region, dict)
            and any(token in RenderStage._source_text_key(region.get("text")).lower()
                    for token in ("coverdesign", "コミックス", "comics", "next"))
            for region in regions
        )
        for fallback_idx, region in enumerate(regions):
            if not isinstance(region, dict):
                continue
            try:
                idx = int(region.get("index", fallback_idx))
            except (TypeError, ValueError):
                continue
            text = region.get("text")
            if region.get("source") != "vision":
                near_key = RenderStage._source_text_similarity_key(text)
                if near_key:
                    ocr_similarity_keys.add(near_key)
                short_name_key = RenderStage._source_text_short_name_key(text)
                if short_name_key:
                    ocr_short_name_keys.add(short_name_key)
                if page_is_contents:
                    continue
                if RenderStage._looks_like_non_dialogue_text(text):
                    suppressed[idx] = "non-dialogue OCR text"
                elif page_has_cover_marker:
                    suppressed[idx] = "cover OCR text"

        for fallback_idx, region in enumerate(regions):
            if not isinstance(region, dict) or region.get("source") != "vision":
                continue
            try:
                idx = int(region.get("index", fallback_idx))
            except (TypeError, ValueError):
                continue
            text = region.get("text")
            near_key = RenderStage._source_text_similarity_key(text)
            if near_key and near_key in ocr_similarity_keys:
                suppressed[idx] = "near-duplicate vision text"
                continue
            short_name_key = RenderStage._source_text_short_name_key(text)
            if short_name_key and any(
                RenderStage._short_name_keys_nearly_match(short_name_key, ocr_key)
                for ocr_key in ocr_short_name_keys
            ):
                suppressed[idx] = "near-duplicate vision name"
                continue
            if page_is_contents:
                continue
            if RenderStage._looks_like_non_dialogue_text(text):
                suppressed[idx] = "non-dialogue vision text"
                continue
            if page_has_cover_marker:
                suppressed[idx] = "cover vision text"
        return suppressed

    @staticmethod
    def _inject_vision_regions(
        payload_path: Path, page_idx: int, context: PipelineContext
    ) -> dict[str, int]:
        """Inject safe vision-detected bubbles as text_regions.

        Runtime OCR geometry is authoritative (docs/render_purity_contract.md).
        Vision bboxes are loose host-side estimates, and the recon-fresh-
        20260624-v4 regression showed that blindly appending all of them paints
        large white bg_color boxes over art. The safe compromise is to keep OCR
        seats untouched, skip any vision bbox that overlaps OCR geometry, and
        append seats only for uncovered vision bubbles. This keeps OCR+vision
        mixed pages from dropping translations without reintroducing white
        occlusion boxes.

        Returns a ``{bubble_id: region_index}`` map for the injected seats so
        the caller can emit translations keyed to the correct index. Idempotent
        across re-runs: already-injected seats are tagged with
        ``source: vision`` and ``bubble_id`` so they are reused instead of
        appended again.

        Vision bubbles without a usable bbox (zero area) are skipped with a
        warning: a seat with no geometry cannot be rendered, and emitting one
        would crash the runtime's font-size resolver.
        """
        page = next((p for p in context.pages if p.page_index == page_idx), None)
        if page is None:
            return {}

        vision_bubbles = [
            b for b in page.bubbles
            if (b.bubble_id.startswith("vision-")
                or getattr(b, "detection_source", None) == "vision")
        ]
        if not vision_bubbles:
            return {}

        suffix = f"-{page_idx:04d}"
        artifact_file = payload_path / f"artifact{suffix}.json"
        if not artifact_file.exists():
            artifact_file = payload_path / "artifact.json"
        if not artifact_file.exists():
            logger.warning(
                "render: cannot inject vision regions for page %d — "
                "artifact missing", page_idx,
            )
            return {}
        try:
            artifact = json.loads(artifact_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("render: cannot read artifact for vision injection (%s)", e)
            return {}

        regions = artifact.setdefault("text_regions", [])
        existing_vision: dict[str, int] = {}
        used_indices: set[int] = set()
        for i, region in enumerate(regions):
            if not isinstance(region, dict):
                continue
            try:
                region_idx = int(region.get("index", i))
            except (TypeError, ValueError):
                continue
            used_indices.add(region_idx)
            if region.get("source") == "vision" and region.get("bubble_id"):
                existing_vision[str(region["bubble_id"])] = region_idx
        occupied_bboxes = [
            bbox
            for region in regions
            if isinstance(region, dict) and region.get("source") != "vision"
            for bbox in [RenderStage._bbox_from_lines(region.get("lines"))]
            if bbox is not None
        ]
        occupied_texts = {
            key
            for region in regions
            if isinstance(region, dict) and region.get("source") != "vision"
            for key in [RenderStage._source_text_key(region.get("text"))]
            if key
        }
        occupied_similarity_texts = {
            key
            for region in regions
            if isinstance(region, dict) and region.get("source") != "vision"
            for key in [RenderStage._source_text_similarity_key(region.get("text"))]
            if key
        }
        occupied_short_name_texts = {
            key
            for region in regions
            if isinstance(region, dict) and region.get("source") != "vision"
            for key in [RenderStage._source_text_short_name_key(region.get("text"))]
            if key
        }

        next_index = max(used_indices, default=-1) + 1
        injected: dict[str, int] = {}
        appended = 0
        page_is_contents = (
            RenderStage._page_is_contents(context, page_idx)
            or RenderStage._artifact_is_contents(payload_path, page_idx)
        )
        contents_columns: list[tuple[float, float, float, float]] = []
        contents_existing_indices: list[int] = []
        contents_column_idx = 0
        contents_existing_idx = 0
        if page_is_contents:
            contents_columns = RenderStage._contents_red_text_columns(
                RenderStage._page_input_image_path(context, page_idx)
            )
            contents_existing_indices = RenderStage._contents_existing_region_indices(
                regions, contents_columns
            )
        for b in vision_bubbles:
            if b.bubble_id in existing_vision:
                injected[b.bubble_id] = existing_vision[b.bubble_id]
                continue
            box_type = str(getattr(b, "box_type", "") or "dialogue").strip().lower()
            is_contents_entry = page_is_contents and box_type not in {"sfx", "graffiti"}
            if is_contents_entry and "contents" in RenderStage._source_text_key(b.source_text).lower():
                continue
            if is_contents_entry and contents_existing_idx < len(contents_existing_indices):
                injected[b.bubble_id] = contents_existing_indices[contents_existing_idx]
                contents_existing_idx += 1
                continue
            if not is_contents_entry and not RenderStage._is_renderable_vision_box_type(box_type):
                logger.info(
                    "render: skipping vision bubble %s on page %d because "
                    "box_type=%s is not a speech-balloon render target",
                    b.bubble_id, page_idx, getattr(b, "box_type", None),
                )
                continue
            source_key = RenderStage._source_text_key(b.source_text)
            if source_key and source_key in occupied_texts:
                logger.info(
                    "render: skipping vision bubble %s on page %d because "
                    "OCR already has the same source text",
                    b.bubble_id, page_idx,
                )
                continue
            similarity_key = RenderStage._source_text_similarity_key(b.source_text)
            if similarity_key and similarity_key in occupied_similarity_texts:
                logger.info(
                    "render: skipping vision bubble %s on page %d because "
                    "OCR already has the same sentence with punctuation drift",
                    b.bubble_id, page_idx,
                )
                continue
            short_name_key = RenderStage._source_text_short_name_key(b.source_text)
            if short_name_key and any(
                RenderStage._short_name_keys_nearly_match(short_name_key, ocr_key)
                for ocr_key in occupied_short_name_texts
            ):
                logger.info(
                    "render: skipping vision bubble %s on page %d because "
                    "OCR already has the same short name with minor OCR drift",
                    b.bubble_id, page_idx,
                )
                continue
            if not is_contents_entry and RenderStage._looks_like_non_dialogue_text(b.source_text):
                logger.info(
                    "render: skipping vision bubble %s on page %d because "
                    "it looks like cover/contents/chapter metadata, not dialogue",
                    b.bubble_id, page_idx,
                )
                continue
            bbox = b.bbox
            if bbox is None or bbox.width <= 0 or bbox.height <= 0:
                logger.info(
                    "render: vision bubble %s on page %d has no usable bbox — "
                    "skipping (cannot render without geometry)",
                    b.bubble_id, page_idx,
                )
                continue
            if is_contents_entry and contents_column_idx < len(contents_columns):
                x, y, w, h = contents_columns[contents_column_idx]
                contents_column_idx += 1
            else:
                x, y, w, h = (
                    float(bbox.x), float(bbox.y), float(bbox.width), float(bbox.height),
                )
            vision_bbox = (x, y, w, h)
            if any(RenderStage._bbox_conflicts(vision_bbox, occupied) for occupied in occupied_bboxes):
                logger.info(
                    "render: skipping vision bubble %s on page %d because "
                    "it overlaps existing OCR geometry",
                    b.bubble_id, page_idx,
                )
                continue
            # lines = quadrilateral polygon [[x,y],[x+w,y],[x+w,y+h],[x,y+h]];
            # the runtime's text renderer uses lines to position + size text.
            region = {
                "index": next_index,
                "source": "vision",
                "bubble_id": b.bubble_id,
                "text": b.source_text or "",
                "texts": [b.source_text or ""],
                "lines": [[[x, y], [x + w, y], [x + w, y + h], [x, y + h]]],
                # font_size: use bbox height (matches OCR detector convention where
                # font_size ≈ text height). -1 = auto-calc, but the runtime's
                # _fit_font_size_to_region binary-searches up to 2×bbox height
                # (e.g. 1822px for a 911px-tall vision bubble), and freetype's
                # set_pixel_sizes(0, 1822) raises FT_Exception: raster overflow.
                # Using bbox height caps the starting font size to a sane value.
                "font_size": max(8, int(round(min(w, h) * 0.45))),
                "angle": 0.0,
                "direction": "auto",
                "alignment": "auto",
                "fg_color": [0, 0, 0],
                "bg_color": [255, 255, 255],
                "source_lang": "ja",
                "target_lang": "CHS",
                "line_spacing": 1.0,
                "letter_spacing": 1.0,
                "bold": False,
                "italic": False,
                "font_weight": 50,
                "default_stroke_width": 0.2,
                "prob": None,
            }
            regions.append(region)
            injected[b.bubble_id] = next_index
            next_index += 1
            appended += 1

        if appended:
            artifact_file.write_text(
                json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            logger.info(
                "render: injected %d vision region(s) into artifact-%s.json "
                "(indices %d..%d)",
                appended, suffix,
                len(regions) - appended, len(regions) - 1,
            )
        return injected

    @staticmethod
    def _bbox_conflicts(
        bbox_a: tuple[float, float, float, float],
        bbox_b: tuple[int, int, int, int],
    ) -> bool:
        coverage = RenderStage._bbox_overlap_coverage(bbox_a, bbox_b)
        if coverage > 0.8:
            return True
        ax, ay, aw, ah = bbox_a
        bx, by, bw, bh = bbox_b
        if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
            return False
        x1 = max(ax, bx)
        y1 = max(ay, by)
        x2 = min(ax + aw, bx + bw)
        y2 = min(ay + ah, by + bh)
        if x2 <= x1 or y2 <= y1:
            return False
        inter = (x2 - x1) * (y2 - y1)
        area_a = aw * ah
        area_b = bw * bh
        union = area_a + area_b - inter
        if union <= 0:
            return False
        iou = inter / union
        return iou > 0.3

    @staticmethod
    def _bbox_overlap_coverage(
        bbox_a: tuple[float, float, float, float] | tuple[int, int, int, int],
        bbox_b: tuple[float, float, float, float] | tuple[int, int, int, int],
    ) -> float:
        ax, ay, aw, ah = bbox_a
        bx, by, bw, bh = bbox_b
        if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
            return 0.0
        x1 = max(ax, bx)
        y1 = max(ay, by)
        x2 = min(ax + aw, bx + bw)
        y2 = min(ay + ah, by + bh)
        if x2 <= x1 or y2 <= y1:
            return 0.0
        inter = (x2 - x1) * (y2 - y1)
        area_a = aw * ah
        area_b = bw * bh
        return inter / min(area_a, area_b)

    @staticmethod
    def _bbox_from_lines(lines: Any) -> tuple[int, int, int, int] | None:
        """Compute an axis-aligned bbox (x, y, w, h) from OCR ``lines`` polygons.

        ``lines`` is a list of polygons, each a list of [x, y] points. Returns
        None when no usable points are present.
        """
        if not lines:
            return None
        try:
            xs: list[float] = []
            ys: list[float] = []
            for poly in lines:
                for pt in poly:
                    xs.append(float(pt[0]))
                    ys.append(float(pt[1]))
            if not xs:
                return None
            x_min, x_max = min(xs), max(xs)
            y_min, y_max = min(ys), max(ys)
            w = x_max - x_min
            h = y_max - y_min
        except (TypeError, ValueError, IndexError):
            return None
        if w <= 0 or h <= 0:
            return None
        return (int(x_min), int(y_min), int(w), int(h))

    @staticmethod
    def _page_input_image_path(context: PipelineContext, page_idx: int) -> str | None:
        """Resolve the original (pre-inpaint) input image path for a page.

        Falls back to None when the page or its image path is unavailable; the
        blank-region check is skipped in that case (fail open — render as usual).
        """
        page = next((p for p in context.pages if p.page_index == page_idx), None)
        if page is None:
            return None
        image = getattr(page, "image", None)
        path = getattr(image, "path", "") if image is not None else ""
        return path or None

    @staticmethod
    def _is_blank_region(image_path: str, bbox: tuple[int, int, int, int]) -> bool:
        """Return True when the bbox area of the input image is essentially blank.

        A region is treated as a blank-background hallucination when it has
        negligible text ink (fewer than ``_BLANK_INK_MIN_FRACTION`` dark pixels)
        AND is a bright/white area. The ink floor is the primary gatekeeper: any
        region with meaningful text ink (even ~1-3% from sparse dialogue in an
        oversized OCR bbox) is KEPT, which avoids false positives on real text.
        Only ink-free regions are then checked for a near-white or flat-bright
        background. Flat dark regions (low std but real content) are never flagged
        because they carry ink.

        Uses PIL + numpy for a cheap pixel sample. Any error reading or decoding
        the image returns False (fail open — don't skip on unreadable input).
        """
        x, y, w, h = bbox
        if w <= 0 or h <= 0:
            return False
        try:
            from PIL import Image

            import numpy as np

            with Image.open(image_path) as img:
                img_w, img_h = img.size
                # Clamp to image bounds; skip if entirely outside.
                x0 = max(0, x)
                y0 = max(0, y)
                x1 = min(img_w, x + w)
                y1 = min(img_h, y + h)
                if x1 <= x0 or y1 <= y0:
                    return False
                crop = img.crop((x0, y0, x1, y1))
                gray = np.asarray(crop.convert("L"), dtype=np.float64)
        except Exception:
            return False
        if gray.size == 0:
            return False
        # Primary gate: real text ink present → not blank (never a hallucination).
        ink_fraction = float((gray < _BLANK_INK_DARKNESS).mean())
        if ink_fraction >= _BLANK_INK_MIN_FRACTION:
            return False
        # No meaningful ink: flag as blank only on a bright/white background.
        near_white_fraction = float((gray > _BLANK_NEAR_WHITE_BRIGHTNESS).mean())
        if near_white_fraction > _BLANK_NEAR_WHITE_FRACTION:
            return True
        std = float(gray.std())
        mean = float(gray.mean())
        # Flat AND bright → blank background. Flat but dark → real content.
        return std < _BLANK_VARIANCE_STD and mean >= _BLANK_NEAR_WHITE_BRIGHTNESS

    def _write_page_translations(
        self, payload_path: Path, context: PipelineContext, cfg: ProjectConfig, page_idx: int
    ) -> None:
        """Write translations for a specific page, including footnotes."""
        prefix = f"region-{page_idx:04d}-"
        source_by_bubble = {
            bubble.bubble_id: bubble.source_text
            for page in context.pages
            for bubble in page.bubbles
            if bubble.bubble_id.startswith(prefix)
        }
        translations = []
        footnotes = []
        seen_footnote_keys: set[tuple[str, str]] = set()

        # S2T converter (cached per stage — instantiated once per RenderStage.execute call).
        # Converts rendered text from simplified to traditional Chinese when
        # cfg.chinese_variant is set. "auto" disables conversion.
        s2t_converter = self._get_s2t_converter(cfg)

        # OCR hallucination guard: load per-region metadata (prob + bbox) from the
        # Pass 1 artifact so we can drop hallucinated blank-background regions and
        # low-confidence detections before the render subprocess runs.
        input_image_path = self._page_input_image_path(context, page_idx)
        page_is_contents = (
            RenderStage._page_is_contents(context, page_idx)
            or RenderStage._artifact_is_contents(payload_path, page_idx)
        )

        # Pin the OCR artifact to I_n by content hash so g(I_n) is deterministic
        # across runs (runtime OCR is otherwise non-deterministic). The pin store
        # is content-addressed on sha256(I_n) and lives in a stable project
        # location so it survives across invocations — the same input image always
        # renders against the same geometry. Default ON (reproducibility goal).
        if self.pin_artifacts and input_image_path:
            try:
                from mga.runtime_bridge.artifact_cache import ArtifactPin, image_sha256, resolve_pinned_artifact
                wd = getattr(cfg, "working_dir", "") or ""
                pin_root = Path(wd) if wd else payload_path
                store = ArtifactPin(pin_root / ".mga_cache" / "artifact-pin.json")
                current_artifact = self._load_artifact(payload_path, page_idx)
                pinned_artifact, was_pinned = resolve_pinned_artifact(payload_path, page_idx, input_image_path, store)
                if was_pinned and current_artifact:
                    page_texts = self._page_source_texts(context, page_idx)
                    pinned_texts = self._artifact_texts(pinned_artifact)
                    current_texts = self._artifact_texts(current_artifact)
                    if (
                        page_texts
                        and pinned_texts
                        and current_texts
                        and pinned_texts.isdisjoint(page_texts)
                        and not current_texts.isdisjoint(page_texts)
                    ):
                        logger.warning(
                            "render: replacing stale pinned artifact for page %d",
                            page_idx,
                        )
                        store.put(image_sha256(input_image_path), current_artifact)
                        self._write_artifact(payload_path, page_idx, current_artifact)
            except Exception as e:  # pragma: no cover — pinning must never break render
                logger.debug("render: artifact pin skipped for page %d (%s)", page_idx, e)

        region_meta = self._load_region_metadata(payload_path, page_idx)

        # Inject vision-detected bubbles only where OCR did not already provide
        # geometry. Blind injection caused the recon-fresh-v4 white-box
        # regression, while no injection drops uncovered vision translations.
        vision_region_index = self._inject_vision_regions(
            payload_path, page_idx, context
        )

        # Reload region metadata so it reflects the freshly-injected vision seats
        # (their bboxes are needed for the blank-region hallucination guard below).
        if vision_region_index:
            region_meta = self._load_region_metadata(payload_path, page_idx)
        valid_region_indices = self._load_artifact_region_indices(payload_path, page_idx)
        artifact_regions_by_index = self._artifact_regions_by_index(payload_path, page_idx)
        contents_columns = (
            RenderStage._contents_red_text_columns(input_image_path)
            if page_is_contents
            else []
        )
        suppressed_region_indices = self._suppressed_region_indices(payload_path, page_idx, context)
        emitted_region_indices: set[int] = set()

        for t in context.translations:
            if t.bubble_id not in vision_region_index and not t.bubble_id.startswith(prefix):
                continue
            # OCR region bubbles (region-NNNN-NNNN): index is the 3rd segment.
            # Vision bubbles (vision-NNNN-NNNN): use the tagged seat appended by
            # _inject_vision_regions when OCR geometry did not cover the bbox.
            is_vision_injected = t.bubble_id in vision_region_index
            if is_vision_injected:
                region_idx = vision_region_index[t.bubble_id]
            else:
                try:
                    region_idx = int(t.bubble_id.split("-")[2])
                except (IndexError, ValueError):
                    continue

            if valid_region_indices is not None and region_idx not in valid_region_indices:
                logger.warning(
                    "render: skipping translation for missing region %d on page %d",
                    region_idx, page_idx,
                )
                continue

            if region_idx in emitted_region_indices:
                logger.info(
                    "render: skipping duplicate translation for region %d on page %d",
                    region_idx, page_idx,
                )
                continue

            content_region = artifact_regions_by_index.get(region_idx)
            if page_is_contents and (
                not self._contents_region_is_title_candidate(content_region)
                or not self._contents_region_overlaps_columns(content_region, contents_columns)
            ):
                logger.info(
                    "render: skipping contents non-title region %d on page %d",
                    region_idx, page_idx,
                )
                continue

            if region_idx in suppressed_region_indices:
                logger.warning(
                    "render: skipping region %d on page %d (%s)",
                    region_idx, page_idx, suppressed_region_indices[region_idx],
                )
                continue

            # Fix 2: drop low-confidence OCR detections (prob below threshold).
            meta = region_meta.get(region_idx)
            if meta is not None and self.ocr_min_prob > 0.0:
                prob = meta.get("prob")
                if prob is not None and prob < self.ocr_min_prob:
                    logger.warning(
                        "render: skipping low-confidence region %d on page %d "
                        "(prob=%.4f < %.2f)",
                        region_idx, page_idx, prob, self.ocr_min_prob,
                    )
                    continue

            # Fix 1: skip OCR regions whose bbox lands on a blank/background area
            # of the input image. Vision-injected seats are excluded because their
            # bboxes come from page-level vision rather than runtime OCR. Contents
            # pages rely on those vision seats for real red text on white paper;
            # applying this OCR guard there deletes every TOC translation.
            if (
                not is_vision_injected
                and not page_is_contents
                and meta is not None
                and input_image_path
                and meta.get("bbox") is not None
            ):
                bbox = meta["bbox"]
                if self._is_blank_region(input_image_path, bbox):
                    logger.warning(
                        "render: skipping blank-text region %d at (%d,%d) on page %d",
                        region_idx, int(bbox[0]), int(bbox[1]), page_idx,
                    )
                    continue

            render_text = self._extract_render_text(t.text)
            if page_is_contents and content_region is not None:
                render_text = self._contents_title_supplement(
                    context,
                    page_idx,
                    content_region.get("text"),
                    render_text,
                )
            if s2t_converter is not None:
                render_text = s2t_converter.convert(render_text)
            translations.append({
                "region_index": region_idx,
                "translation": render_text,
                "target_lang": _normalize_runtime_lang_code(cfg.target_lang or "CHS"),
            })
            emitted_region_indices.add(region_idx)

            # Name footnotes are intentionally disabled by product rule.

        # Term footnotes: prefer the page-level compiled set (deduplicated,
        # database-enriched explanations, all explanatory types). Fall back to
        # bubble-level candidates when compilation has not run.
        page_obj = next(
            (p for p in context.pages if p.page_index == page_idx),
            None,
        )
        compiled = list(getattr(page_obj, "page_footnotes", []) or []) if page_obj else []
        if compiled:
            for fn in compiled:
                original = self._sanitize_footnote_text(fn.term)
                translation = self._sanitize_footnote_text(fn.translation)
                if not original or not translation:
                    continue
                key = (original, translation)
                if key in seen_footnote_keys:
                    continue
                seen_footnote_keys.add(key)
                footnotes.append({
                    "original": original,
                    "translation": translation,
                    "type": fn.type,
                    "explanation": self._sanitize_footnote_text(fn.explanation),
                })
        else:
            for t in context.translations:
                if t.bubble_id not in vision_region_index and not t.bubble_id.startswith(prefix):
                    continue
                for fn in t.footnotes:
                    original = self._sanitize_footnote_text(fn.original)
                    translation = self._sanitize_footnote_text(fn.translation)
                    if not original or not translation:
                        continue
                    if fn.type not in {"loanword", "sfx", "visual", "cultural", "coined", "fictional"}:
                        continue
                    key = (original, translation)
                    if key in seen_footnote_keys:
                        continue
                    seen_footnote_keys.add(key)
                    footnotes.append({
                        "original": original,
                        "translation": translation,
                        "type": fn.type,
                        "explanation": self._sanitize_footnote_text(fn.explanation or ""),
                    })

        for page in context.pages:
            if page.page_index != page_idx:
                continue
            for fn in getattr(page, "visual_footnotes", []):
                original = self._sanitize_footnote_text(fn.source_text)
                translation = self._sanitize_footnote_text(fn.translation_hint or fn.notes or "见图中文字")
                if not original:
                    continue
                key = (original, translation)
                if key in seen_footnote_keys:
                    continue
                seen_footnote_keys.add(key)
                footnotes.append({
                    "original": original,
                    "translation": translation,
                    "type": "visual",
                    "kind": fn.kind,
                })

        # render_only uses text_regions to drive both masking/inpainted content
        # and text placement. If we only suppress translations, non-dialogue
        # pages still render from Pass 1's inpainted holes: page-001/page-003
        # became mostly white even with translations=[]. Keep artifact,
        # inpainted image, and translations in one index space.
        self._prune_artifact_to_rendered_regions(
            payload_path,
            page_idx,
            translations,
            input_image_path,
        )
        if page_is_contents or not translations:
            footnotes = []
        elif not getattr(cfg, "render_footnotes", False):
            footnotes = []

        payload = {
            "version": 1,
            "target_lang": _normalize_runtime_lang_code(cfg.target_lang or "CHS"),
            "translations": translations,
            "footnotes": footnotes,
        }
        suffix = f"-{page_idx:04d}"
        (payload_path / f"translations{suffix}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _extract_render_text(raw_text: str) -> str:
        """Extract translatable text from plain text or JSON-like model output.

        Handles JSON objects, Python dict reprs (single-quoted), and
        JSON embedded in surrounding text. Falls back to regex extraction
        of a ``"text"`` field, then noise stripping.
        """
        text = (raw_text or "").strip()
        if not text:
            return text

        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1]).strip()

        parsed = None
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
            # Fallback: LLMs sometimes return Python dict repr (single
            # quotes) instead of valid JSON.
            if parsed is None:
                try:
                    import ast
                    evaluated = ast.literal_eval(text)
                    if isinstance(evaluated, dict):
                        parsed = evaluated
                except (ValueError, SyntaxError):
                    pass
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                except Exception:
                    parsed = None
                if parsed is None:
                    try:
                        import ast
                        evaluated = ast.literal_eval(text[start : end + 1])
                        if isinstance(evaluated, dict):
                            parsed = evaluated
                    except (ValueError, SyntaxError):
                        pass

        if isinstance(parsed, dict):
            extracted = parsed.get("text") or parsed.get("translation")
            if isinstance(extracted, str) and extracted.strip():
                return RenderStage._clean_render_text(extracted.strip())

        # Fallback: extract text field from malformed JSON-like output.
        # Handles both JSON ("text": "...") and Python dict repr ('text': '...').
        m = re.search(r'"text"\s*:\s*"((?:\\.|[^"\\])*)"', text, flags=re.DOTALL)
        if m:
            try:
                extracted = json.loads(f'"{m.group(1)}"')
                if isinstance(extracted, str) and extracted.strip():
                    return RenderStage._clean_render_text(extracted.strip())
            except Exception:
                pass
        m = re.search(r"'text'\s*:\s*'((?:\\.|[^'\\])*)'", text, flags=re.DOTALL)
        if m:
            extracted = m.group(1).replace("\\'", "'")
            if extracted.strip():
                return RenderStage._clean_render_text(extracted.strip())

        text = RenderStage._strip_json_noise(text)
        return RenderStage._clean_render_text(text)

    @staticmethod
    def _clean_render_text(text: str) -> str:
        """Final render-text cleaning: strip LLM chatter/markdown labels, then
        inline footnote noise. Applied on every extraction path."""
        s = RenderStage._strip_inline_footnote_noise(
            RenderStage._strip_llm_chatter(text)
        )
        # Collapse LLM-introduced line breaks and extra spaces. Manga dialogue
        # text should be a single line — the runtime handles wrapping.
        s = re.sub(r"\s*\n\s*", " ", s).strip()
        s = re.sub(r" {2,}", " ", s)
        return s

    @staticmethod
    def _strip_llm_chatter(text: str) -> str:
        """Strip LLM chatter that leaks into translation output.

        Catches markdown labels emitted by re-translate / QA paths, e.g.
        '**Corrected Translation:**', '**Translation:**', '**译文：**',
        'Translation:'. Manga dialogue never begins with a bold markdown label,
        so stripping a leading '**<label>:**' (or a plain 'Label:') is safe.
        """
        s = (text or "").strip()
        if not s:
            return s
        # Leading markdown bold label: **...:**  (label has no '*' / newline / colon)
        s = re.sub(r"^\s*\*\*[^*\n：:]{1,40}[:：]\*\*[\s]*", "", s).strip()
        # Leading plain English/CJK label followed by a colon.
        s = re.sub(
            r"^\s*(?:Translation|Corrected\s+Translation|Final\s+Translation|"
            r"译文|修正翻译|最终译文|最终翻译|翻译)\s*[:：]\s*",
            "", s, flags=re.IGNORECASE,
        ).strip()
        # Whole-string markdown bold wrapping the translation.
        if s.startswith("**") and s.endswith("**") and s.count("**") == 2:
            s = s[2:-2].strip()
        return s

    @staticmethod
    def _strip_inline_footnote_noise(text: str) -> str:
        """Remove common inline footnote tails from bubble text.

        Footnotes should be rendered only by dedicated footnote overlay.
        """
        s = (text or "").strip()
        if not s:
            return s
        # Remove trailing bracket notes like "（xx）"/"(xx)" often used as inline footnotes.
        s = re.sub(r"[（(][^)）]{1,24}[)）]\s*$", "", s).strip()
        # Remove explicit footnote label tails, e.g. "※ xxx"
        s = re.sub(r"\s*※\s*.*$", "", s).strip()
        return s

    @staticmethod
    def _strip_json_noise(text: str) -> str:
        """Strip obvious JSON scaffolding that should never be rendered in bubble text."""
        s = (text or "").strip()
        if not s:
            return s
        # Remove known JSON keys if they leak as plain text.
        s = re.sub(r'"(?:footnotes|rationale|confidence|original|translation|type)"\s*:\s*', "", s)
        # Remove leftover braces/brackets that usually come from JSON blobs.
        s = re.sub(r"[{}\[\]]", "", s)
        # Remove markdown-fence tag remnants.
        s = s.replace("json", "").replace("```", "")
        return s.strip()

    @staticmethod
    def _sanitize_footnote_text(text: str) -> str:
        """Keep footnote fields human-readable and JSON-free."""
        s = (text or "").strip()
        if not s:
            return s
        if s.startswith("```"):
            lines = s.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                s = "\n".join(lines[1:-1]).strip()
        # Try to extract from malformed key-value form.
        m = re.search(r'"(?:text|translation|original)"\s*:\s*"((?:\\.|[^"\\])*)"', s, flags=re.DOTALL)
        if m:
            try:
                s = json.loads(f'"{m.group(1)}"')
            except Exception:
                pass
        s = RenderStage._strip_json_noise(s)
        return s.strip()

    @classmethod
    def _get_s2t_converter(cls, cfg: ProjectConfig):
        """Get a cached S2T converter for the configured Chinese variant.

        Returns None if variant is "auto" (no conversion). The converter is
        memoized at module scope, keyed only by variant, so it is
        deterministic and does not affect the rendered output — it exists
        purely to avoid rebuilding the converter once per page.
        """
        variant = getattr(cfg, "chinese_variant", "auto") or "auto"
        if variant in ("auto", "", None):
            return None
        cache = _S2T_CONVERTER_CACHE
        if variant not in cache:
            try:
                from mga.cultural.s2t_converter import S2TConverter
                cache[variant] = S2TConverter(variant)
            except ImportError:
                cache[variant] = None
        return cache.get(variant)

