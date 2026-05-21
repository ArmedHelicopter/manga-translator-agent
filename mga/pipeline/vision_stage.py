"""Stage 2 -- Vision extraction via LLM provider."""

from __future__ import annotations

from pathlib import Path

from mga.models import Bubble, ProjectConfig
from mga.providers import select_provider

from .stages import PipelineContext, PipelineStage


def _build_vision_prompt() -> str:
    return (
        "Analyze this manga page. For each speech bubble, extract:\n"
        "- bubble_id (sequential), source_text, speaker_id, tone\n"
        "Also provide a one-sentence scene_summary.\n"
        "Return structured JSON with 'bubbles' and 'scene_summary'."
    )


class VisionStage(PipelineStage):
    """Use LLM vision to extract bubble text and scene summaries per page."""

    @property
    def name(self) -> str:
        return "vision"

    @property
    def order(self) -> int:
        return 20

    def execute(self, context: PipelineContext) -> PipelineContext:
        cfg: ProjectConfig = context.project_config
        provider = self._get_provider(cfg)

        extractions: list[dict] = []
        for page in context.pages:
            result = self._extract_page(provider, page, cfg)
            extractions.append(result)
            self._apply_to_page(page, result)

        context.artifacts[self.name] = {"extractions": extractions}
        return context

    def _get_provider(self, cfg: ProjectConfig) -> object:
        route = cfg.provider_routes.get("vision")
        if route:
            return select_provider(route.primary.model or "openai")
        return select_provider("openai")

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
