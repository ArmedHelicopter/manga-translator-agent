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
        """Read OCR results from a runtime-exported artifact.json."""
        artifact_path = Path(payload_dir) / "artifact.json"
        artifact_data = json.loads(artifact_path.read_text(encoding="utf-8"))

        regions = artifact_data.get("text_regions", [])
        page = context.pages[0] if context.pages else None
        if not page:
            context.artifacts[self.name] = {"source": "artifact", "regions": 0}
            return context

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
                bubble_id=f"region-{i:04d}",
                bbox=bbox,
                source_text=region.get("text", ""),
                reading_order=i,
            ))

        page.scene_summary = f"Page with {len(regions)} text regions (from runtime OCR)"
        context.artifacts[self.name] = {
            "source": "artifact",
            "payload_dir": payload_dir,
            "regions": len(regions),
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
            return get_provider(name, model=route.primary.model, **settings)
        return get_provider("openai")

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
        for b in bubbles_raw:
            page.bubbles.append(Bubble(
                bubble_id=b.get("bubble_id", ""),
                source_text=b.get("source_text", ""),
                speaker_id=b.get("speaker_id"),
                speaker_name=b.get("speaker_name"),
                tone=b.get("tone"),
            ))
        page.scene_summary = result.get("scene_summary", "")
