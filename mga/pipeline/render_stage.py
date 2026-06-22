"""Stage 6 -- Rendering via external runtime (two-pass mode)."""

from __future__ import annotations

import json
import logging
import re
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

        # Pin the OCR artifact to I_n by content hash so g(I_n) is deterministic
        # across runs (runtime OCR is otherwise non-deterministic). The pin store
        # is content-addressed on sha256(I_n) and lives in a stable project
        # location so it survives across invocations — the same input image always
        # renders against the same geometry. Default ON (reproducibility goal).
        if self.pin_artifacts and input_image_path:
            try:
                from mga.runtime_bridge.artifact_cache import ArtifactPin, resolve_pinned_artifact
                wd = getattr(cfg, "working_dir", "") or ""
                pin_root = Path(wd) if wd else payload_path
                store = ArtifactPin(pin_root / ".mga_cache" / "artifact-pin.json")
                resolve_pinned_artifact(payload_path, page_idx, input_image_path, store)
            except Exception as e:  # pragma: no cover — pinning must never break render
                logger.debug("render: artifact pin skipped for page %d (%s)", page_idx, e)

        region_meta = self._load_region_metadata(payload_path, page_idx)

        for t in context.translations:
            if not t.bubble_id.startswith(prefix):
                continue
            try:
                region_idx = int(t.bubble_id.split("-")[2])
            except (IndexError, ValueError):
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

            # Fix 1: skip regions whose bbox lands on a blank/background area of
            # the input image (OCR hallucination on pure-white TOC/cover areas).
            if meta is not None and input_image_path and meta.get("bbox") is not None:
                bbox = meta["bbox"]
                if self._is_blank_region(input_image_path, bbox):
                    logger.warning(
                        "render: skipping blank-text region %d at (%d,%d) on page %d",
                        region_idx, int(bbox[0]), int(bbox[1]), page_idx,
                    )
                    continue

            render_text = self._extract_render_text(t.text)
            if s2t_converter is not None:
                render_text = s2t_converter.convert(render_text)
            translations.append({
                "region_index": region_idx,
                "translation": render_text,
                "target_lang": _normalize_runtime_lang_code(cfg.target_lang or "CHS"),
            })

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
                if not t.bubble_id.startswith(prefix):
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
        """Extract translatable text from plain text or JSON-like model output."""
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
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                except Exception:
                    parsed = None

        if isinstance(parsed, dict):
            extracted = parsed.get("text") or parsed.get("translation")
            if isinstance(extracted, str) and extracted.strip():
                return RenderStage._clean_render_text(extracted.strip())

        # Fallback: extract text field from malformed JSON-like output.
        m = re.search(r'"text"\s*:\s*"((?:\\.|[^"\\])*)"', text, flags=re.DOTALL)
        if m:
            try:
                extracted = json.loads(f'"{m.group(1)}"')
                if isinstance(extracted, str) and extracted.strip():
                    return RenderStage._clean_render_text(extracted.strip())
            except Exception:
                pass

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

