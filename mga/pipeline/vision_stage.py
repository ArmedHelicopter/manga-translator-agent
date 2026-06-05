"""Stage 2 -- OCR artifact loading plus Vision enrichment."""

from __future__ import annotations

import json
from pathlib import Path

from mga.models import BoundingBox, Bubble, ProjectConfig, VisualFootnote
from mga.providers import ProviderCascade

from .stages import PipelineContext, PipelineStage


def _build_vision_prompt() -> str:
    return (
        "Analyze this manga page as visual enrichment for an OCR-first manga translation pipeline.\n"
        "Do not replace OCR text. For each existing OCR bubble, return optional metadata keyed by bubble_id:\n"
        "- box_type: dialogue, narration, sfx, sign, letter, graffiti, or other\n"
        "- provisional_speaker: temporary visible speaker label, not final attribution\n"
        "- voice_hint: speech style hints such as politeness, catchphrases, tone, register\n"
        "- tone and notes if visually inferable\n"
        "Also detect author-drawn or OCR-missed text such as signs, letters, graffiti, and hand lettering.\n"
        "Return JSON with keys: bubbles, visual_footnotes, voice_hints, scene_summary.\n"
        "visual_footnotes items should include source_text, translation_hint, kind, optional bbox, and notes."
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
        return context


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
        if context.metadata.get("artifact_payload_dir"):
            context.artifacts[self.name] = {
                "source": "ocr-artifact",
                "enrichment": "skipped",
                "note": "Runtime OCR artifact contained no text regions; skipping vision fallback.",
            }
            return context
        return self._execute_from_llm(context, cfg)

    def _execute_from_llm(self, context: PipelineContext, cfg: ProjectConfig) -> PipelineContext:
        """Original LLM vision extraction path."""
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
        provider_cascade = ProviderCascade(cfg, "vision")
        enrichments: list[dict] = []
        errors: list[dict] = []
        provider_errors: list[dict] = []
        provider_calls: list[dict] = []
        for page in context.pages:
            try:
                result = self._extract_page(provider_cascade, page, cfg)
                enrichments.append({"page_id": page.page_id, "result": result})
                self._apply_enrichment_to_page(page, result)
                provider_errors.extend(provider_cascade.errors)
                provider_cascade.errors.clear()
                provider_calls.extend(provider_cascade.calls)
                provider_cascade.calls.clear()
            except Exception as exc:
                errors.append({"page_id": page.page_id, "error": str(exc)})

        existing = dict(context.artifacts.get(self.name, {}))
        existing.update({
            "source": source,
            "enrichment": "vision",
            "enriched_pages": len(enrichments),
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
        context.artifacts[self.name] = existing
        return context

    def _extract_page(self, provider_cascade: ProviderCascade, page: object, cfg: ProjectConfig) -> dict:
        img_path = Path(page.image.path)
        if not img_path.exists():
            return {"bubbles": [], "scene_summary": ""}

        image_bytes = img_path.read_bytes()
        prompt = _build_vision_prompt()

        try:
            result, _candidate = provider_cascade.call_vision_structured(
                messages=[{"role": "user", "content": prompt}],
                images=[image_bytes],
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
        for i, b in enumerate(bubbles_raw):
            raw_id = str(b.get("bubble_id", i + 1))
            bubble_id = f"{page.page_id}-{raw_id}"
            page.bubbles.append(Bubble(
                bubble_id=bubble_id,
                source_text=str(b.get("source_text", "")),
                reading_order=int(b.get("reading_order", i)),
                speaker_id=b.get("speaker_id"),
                speaker_name=b.get("speaker_name"),
                tone=b.get("tone"),
                notes=b.get("notes"),
                box_type=b.get("box_type", "dialogue") or "dialogue",
                provisional_speaker=b.get("provisional_speaker") or b.get("speaker_name"),
                voice_hint=b.get("voice_hint"),
                vision_notes=b.get("vision_notes") or b.get("notes"),
            ))
        self._apply_page_level_enrichment(page, result)
        page.scene_summary = result.get("scene_summary", "")

    def _apply_enrichment_to_page(self, page: object, result: dict) -> None:
        by_id = {bubble.bubble_id: bubble for bubble in page.bubbles}
        by_order = {bubble.reading_order: bubble for bubble in page.bubbles}
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
