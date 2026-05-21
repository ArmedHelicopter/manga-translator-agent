"""Stage 6 -- Rendering (external runtime responsibility)."""

from __future__ import annotations

from mga.models import ProjectConfig, TranslatedPage

from .stages import PipelineContext, PipelineStage


class RenderStage(PipelineStage):
    """Stub stage -- rendering is delegated to the external manga-image-translator.

    This stage passes translations through to the artifacts and records
    that rendering will be handled externally.
    """

    @property
    def name(self) -> str:
        return "render"

    @property
    def order(self) -> int:
        return 60

    def execute(self, context: PipelineContext) -> PipelineContext:
        cfg: ProjectConfig = context.project_config
        translated_pages: list[TranslatedPage] = []

        for page in context.pages:
            page_translations = [
                t for t in context.translations
                if t.bubble_id in {b.bubble_id for b in page.bubbles}
            ]
            translated_pages.append(TranslatedPage(
                index=page.page_index,
                image_path=page.image.path,
                page_json={
                    "page_id": page.page_id,
                    "translations": [t.model_dump() for t in page_translations],
                },
            ))

        context.artifacts[self.name] = {
            "mode": "external",
            "pages": [p.model_dump() for p in translated_pages],
            "note": "Rendering delegated to manga-image-translator runtime",
        }
        return context
