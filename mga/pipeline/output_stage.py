"""Stage 7 -- Output writing, manifest, run summary, and translation report."""

from __future__ import annotations

import json
from pathlib import Path

from mga.format import get_adapter
from mga.models import ProjectConfig, TranslatedPage

from .stages import PipelineContext, PipelineStage


class OutputStage(PipelineStage):
    """Write translated output, manifest, run summary, QA report, and translation report."""

    @property
    def name(self) -> str:
        return "output"

    @property
    def order(self) -> int:
        return 70

    def execute(self, context: PipelineContext) -> PipelineContext:
        cfg: ProjectConfig = context.project_config

        if cfg.pipeline_mode == "novel":
            return self._execute_novel(cfg, context)

        output_dir = Path(cfg.output_dir) if cfg.output_dir else Path("output")
        output_dir.mkdir(parents=True, exist_ok=True)

        from mga.artifacts.store import ArtifactStore
        store = ArtifactStore(output_dir)
        self._write_manifest(output_dir, context, cfg)
        self._write_run_summary(store, context, cfg)
        self._write_qa_report(store, context)
        self._write_translation_report(store, context)

        context.artifacts[self.name] = {
            "output_dir": str(output_dir),
            "files_written": [
                "manifest.json", "run.json", "qa_report.json",
                "translation-report.json",
            ],
        }
        return context

    def _execute_novel(self, cfg: ProjectConfig, context: PipelineContext) -> PipelineContext:
        output_path = Path(context.metadata.get("output_path", cfg.output_dir or "output"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        adapter = get_adapter(f"novel-{cfg.input_format}")

        # Build TranslatedPage objects from translations
        translation_by_id = {t.bubble_id: t for t in context.translations}
        translated_pages: list[TranslatedPage] = []

        for page in context.pages:
            translated_parts: list[str] = []
            for bubble in sorted(page.bubbles, key=lambda b: b.reading_order):
                candidate = translation_by_id.get(bubble.bubble_id)
                translated_parts.append(candidate.text if candidate else bubble.source_text)

            novel_meta = getattr(page, "_novel_meta", {})
            translated_pages.append(TranslatedPage(
                index=page.page_index,
                image_path="",
                page_json={
                    "translated_text": "\n".join(translated_parts),
                    "chapter_title": page.scene_summary,
                    "xhtml_entry": novel_meta.get("xhtml_entry", ""),
                    "chunk_index": novel_meta.get("chunk_index", 0),
                    "original_epub_path": context.metadata.get("input_path", ""),
                },
            ))

        adapter.repack(iter(translated_pages), output_path)

        context.artifacts[self.name] = {
            "output_path": str(output_path),
            "mode": "novel",
        }
        # Write run summary, QA report, and translation report alongside output
        output_dir = output_path.parent
        from mga.artifacts.store import ArtifactStore
        store = ArtifactStore(output_dir)
        self._write_run_summary(store, context, cfg)
        self._write_qa_report(store, context)
        self._write_translation_report(store, context)
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

    def _write_run_summary(self, store, ctx: PipelineContext, cfg: ProjectConfig) -> None:
        from mga.artifacts.run_summary import build_run_summary, write_run_summary
        summary = build_run_summary(ctx, cfg)
        write_run_summary(store, summary)

    def _write_qa_report(self, store, ctx: PipelineContext) -> None:
        if not ctx.qa_report:
            return
        store.write_qa_report(ctx.qa_report)

    def _write_translation_report(self, store, ctx: PipelineContext) -> None:
        from mga.artifacts.translation_report import build_translation_report, write_translation_report
        report = build_translation_report(ctx)
        write_translation_report(store, report)
