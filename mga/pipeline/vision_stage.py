"""Stage 2 -- Vision extraction via LLM provider or runtime artifact."""

from __future__ import annotations

import json
from pathlib import Path

from mga.models import BoundingBox, Bubble, ProjectConfig
from mga.providers import get_provider

from .stages import PipelineContext, PipelineStage


def _build_vision_prompt() -> str:
    return (
        "Analyze this manga page. For each speech bubble, extract:\n"
        "- bubble_id (sequential), source_text, speaker_id, tone\n"
        "Also provide a one-sentence scene_summary.\n"
        "Return structured JSON with 'bubbles' and 'scene_summary'."
    )


class VisionStage(PipelineStage):
    """Use LLM vision or runtime artifact to extract bubble text per page."""

    @property
    def name(self) -> str:
        return "vision"

    @property
    def order(self) -> int:
        return 20

    def execute(self, context: PipelineContext) -> PipelineContext:
        cfg: ProjectConfig = context.project_config
        payload_dir = context.metadata.get("artifact_payload_dir")

        if payload_dir:
            return self._execute_from_artifact(context, payload_dir)
        return self._execute_from_llm(context, cfg)

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

    def _execute_from_llm(self, context: PipelineContext, cfg: ProjectConfig) -> PipelineContext:
        """Original LLM vision extraction path."""
        provider = self._get_provider(cfg)

        extractions: list[dict] = []
        for page in context.pages:
            result = self._extract_page(provider, page, cfg)
            extractions.append(result)
            self._apply_to_page(page, result)

        context.artifacts[self.name] = {"source": "llm", "extractions": extractions}
        return context

    def _get_provider(self, cfg: ProjectConfig) -> object:
        route = cfg.provider_routes.get("vision")
        if route and route.primary.provider:
            name = route.primary.provider
            settings = cfg.provider_settings.get(name, {})
            if route.primary.model and "model" not in settings:
                settings["model"] = route.primary.model
            return get_provider(name, **settings)
        settings = cfg.provider_settings.get("openai", {})
        return get_provider("openai", **settings)

    def _extract_page(self, provider: object, page: object, cfg: ProjectConfig) -> dict:
        img_path = Path(page.image.path)
        if not img_path.exists():
            return {"bubbles": [], "scene_summary": ""}

        image_bytes = img_path.read_bytes()
        prompt = _build_vision_prompt()

        if hasattr(provider, "vision_structured"):
            return provider.vision_structured(
                messages=[{"role": "user", "content": prompt}],
                images=[image_bytes],
                schema={"type": "object", "properties": {"bubbles": {"type": "array"}, "scene_summary": {"type": "string"}}},
            )
        raw = provider.vision(
            messages=[{"role": "user", "content": prompt}],
            images=[image_bytes],
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
                speaker_id=b.get("speaker_id"),
                speaker_name=b.get("speaker_name"),
                tone=b.get("tone"),
            ))
        page.scene_summary = result.get("scene_summary", "")
