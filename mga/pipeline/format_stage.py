"""Stage 1 -- Format detection and page extraction."""

from __future__ import annotations

from pathlib import Path

from mga.format import get_adapter
from mga.models import Bubble, Page, PageImage, ProjectConfig

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
        input_path = Path(context.metadata.get("input_path", cfg.working_dir or "."))

        if cfg.pipeline_mode == "novel":
            return self._execute_novel(cfg, input_path, context)
        return self._execute_manga(cfg, input_path, context)

    def _execute_manga(self, cfg: ProjectConfig, input_path: Path, context: PipelineContext) -> PipelineContext:
        # Check for runtime payload - use pre-extracted pages if available
        payload_dir = context.metadata.get("artifact_payload_dir", "")
        if payload_dir and Path(payload_dir).exists():
            pages = self._load_from_runtime_payload(Path(payload_dir))
            if pages:
                context.pages = pages
                context.artifacts[self.name] = {
                    "page_count": len(pages),
                    "format": cfg.input_format,
                    "source": "artifact_payload",
                }
                return context

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

    def _load_from_runtime_payload(self, payload_dir: Path) -> list[Page]:
        """Load pre-extracted pages from runtime payload directory."""
        import json as _json

        pages_json = payload_dir / "pages.json"
        runtime_input = payload_dir / ".runtime-input"

        if not pages_json.exists() or not runtime_input.exists():
            return []

        try:
            pages_meta = _json.loads(pages_json.read_text(encoding="utf-8"))
        except Exception:
            return []

        pages = []
        for page_meta in pages_meta:
            page_index = page_meta.get("page_index", 0)
            image_path = runtime_input / f"page-{page_index:04d}.png"
            if image_path.exists():
                pages.append(Page(
                    page_id=f"page_{page_index:04d}",
                    page_index=page_index,
                    image=PageImage(path=str(image_path)),
                    source_lang="ja",
                ))

        return pages

    def _execute_novel(self, cfg: ProjectConfig, input_path: Path, context: PipelineContext) -> PipelineContext:
        adapter = get_adapter(f"novel-{cfg.input_format}")
        pages: list[Page] = []

        for page_ref in adapter.extract(input_path):
            chapter_text = page_ref.metadata.get("chapter_text", "")
            chunks = chapter_text.split("\n") if chapter_text else [""]
            bubbles = [
                Bubble(
                    bubble_id=f"p{page_ref.index:04d}_b{ci:04d}",
                    source_text=chunk,
                    reading_order=ci,
                )
                for ci, chunk in enumerate(chunks) if chunk.strip()
            ]
            if not bubbles:
                bubbles = [Bubble(bubble_id=f"p{page_ref.index:04d}_b0000", source_text="")]

            page = Page(
                page_id=f"page_{page_ref.index:04d}",
                page_index=page_ref.index,
                source_lang=cfg.source_lang,
                source_text=chapter_text,
                bubbles=bubbles,
                scene_summary=page_ref.metadata.get("chapter_title", ""),
            )
            # Carry adapter metadata through for output stage
            page._novel_meta = page_ref.metadata  # type: ignore[attr-defined]
            pages.append(page)

        context.pages = pages
        context.artifacts[self.name] = {
            "page_count": len(pages),
            "format": f"novel-{cfg.input_format}",
        }
        return context
