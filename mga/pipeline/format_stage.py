"""Stage 1 -- Format detection and page extraction."""

from __future__ import annotations

from pathlib import Path

from mga.format import get_adapter
from mga.models import Page, PageImage, ProjectConfig

from .stages import PipelineContext, PipelineStage


class FormatStage(PipelineStage):
    """Detect input format, extract PageRef objects, and build Page models."""

    @property
    def name(self) -> str:
        return "format"

    @property
    def order(self) -> int:
        return 10

    def execute(self, context: PipelineContext) -> PipelineContext:
        cfg: ProjectConfig = context.project_config
        input_path = Path(cfg.working_dir) if cfg.working_dir else Path(".")

        adapter = get_adapter(cfg.input_format)
        pages: list[Page] = []

        for page_ref in adapter.extract(input_path):
            page = Page(
                page_id=f"page_{page_ref.index:04d}",
                page_index=page_ref.index,
                image=PageImage(path=page_ref.image_path),
                source_lang=cfg.source_lang,
            )
            pages.append(page)

        context.pages = pages
        context.artifacts[self.name] = {
            "page_count": len(pages),
            "format": cfg.input_format,
        }
        return context
