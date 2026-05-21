"""Stage 7 -- Output writing and manifest generation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from mga.format import get_adapter
from mga.models import ProjectConfig, TranslatedPage

from .stages import PipelineContext, PipelineStage


class OutputStage(PipelineStage):
    """Write translated output, manifest, run summary, and QA report."""

    @property
    def name(self) -> str:
        return "output"

    @property
    def order(self) -> int:
        return 70

    def execute(self, context: PipelineContext) -> PipelineContext:
        cfg: ProjectConfig = context.project_config
        output_dir = Path(cfg.output_dir) if cfg.output_dir else Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)

        self._write_manifest(output_dir, context, cfg)
        self._write_run_json(output_dir, context)
        self._write_qa_report(output_dir, context)

        context.artifacts[self.name] = {
            "output_dir": str(output_dir),
            "files_written": [
                "manifest.json", "run.json", "qa_report.json",
            ],
        }
        return context

    def _write_manifest(self, output_dir: Path, ctx: PipelineContext, cfg: ProjectConfig) -> None:
        pages_data = []
        for page in ctx.pages:
            page_translations = [
                t.model_dump() for t in ctx.translations
                if t.bubble_id in {b.bubble_id for b in page.bubbles}
            ]
            pages_data.append({
                "page_id": page.page_id,
                "index": page.page_index,
                "image_path": page.image.path,
                "translations": page_translations,
            })

        manifest = {
            "project_name": cfg.project_name,
            "source_lang": cfg.source_lang,
            "target_lang": cfg.target_lang,
            "page_count": len(ctx.pages),
            "pages": pages_data,
        }
        (output_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _write_run_json(self, output_dir: Path, ctx: PipelineContext) -> None:
        run = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stages_completed": list(ctx.artifacts.keys()),
            "error_count": len(ctx.errors),
            "metadata": ctx.metadata,
        }
        (output_dir / "run.json").write_text(
            json.dumps(run, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def _write_qa_report(self, output_dir: Path, ctx: PipelineContext) -> None:
        if not ctx.qa_report:
            return
        (output_dir / "qa_report.json").write_text(
            json.dumps(ctx.qa_report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
