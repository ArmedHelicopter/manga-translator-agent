"""Stage 7 -- Output writing, manifest, run summary, and translation report."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from mga.format import get_adapter
from mga.models import ProjectConfig, TranslatedPage

from .parsers import clean_translation_text
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

        # Normalize translation text: strip any LLM chatter / markdown labels so
        # neither the translation JSON nor downstream repacked output ever
        # contains them (defense-in-depth alongside the render-stage strip).
        for translation in context.translations:
            if translation.text:
                translation.text = clean_translation_text(translation.text)

        if cfg.pipeline_mode == "novel":
            return self._execute_novel(cfg, context)

        output_format = cfg.output_format or "images"
        output_dir = self._resolve_manga_output_dir(cfg, context, output_format)
        output_dir.mkdir(parents=True, exist_ok=True)

        from mga.artifacts.store import ArtifactStore
        store = ArtifactStore(output_dir)
        self._write_manifest(output_dir, context, cfg)
        translation_history_files = self._write_translation_history(store, context)
        self._write_run_summary(store, context, cfg)
        if cfg.save_artifacts:
            self._write_qa_report(store, context)
            self._write_translation_report(store, context)

        report_output = None
        if output_format == "report":
            report_output = self._write_report_output(output_dir, context, cfg)
        elif output_format != "images":
            self._repack_to_format(output_dir, context, cfg, output_format)

        files_written = [
            "manifest.json",
            "run.json",
        ]
        files_written.extend(Path(item).as_posix() for item in translation_history_files)
        if cfg.save_artifacts:
            files_written.extend([
                "qa_report.json",
                "translation-report.json",
            ])
        if report_output is not None:
            files_written.append(str(report_output))

        context.artifacts[self.name] = {
            "output_dir": str(output_dir),
            "output_format": output_format,
            "files_written": files_written,
        }
        if report_output is not None:
            context.artifacts[self.name]["report_output"] = str(report_output)
        return context

    def _resolve_manga_output_dir(
        self,
        cfg: ProjectConfig,
        ctx: PipelineContext,
        output_format: str,
    ) -> Path:
        output_dir = Path(cfg.output_dir) if cfg.output_dir else Path("output")
        if output_format == "report":
            requested_output = Path(ctx.metadata.get("output_path", output_dir))
            if requested_output.suffix.lower() == ".json":
                return requested_output.parent
        return output_dir

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
        if cfg.save_artifacts:
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

    def _write_translation_history(self, store, ctx: PipelineContext) -> list[str]:
        files_written: list[str] = []
        translation_by_id = {t.bubble_id: t for t in ctx.translations}
        for page in ctx.pages:
            bubbles = [
                {
                    "bubble_id": bubble.bubble_id,
                    "source_text": bubble.source_text,
                    "speaker_id": bubble.speaker_id,
                    "speaker_name": bubble.speaker_name,
                    "reading_order": bubble.reading_order,
                }
                for bubble in page.bubbles
            ]
            page_translations = [
                translation_by_id[bubble.bubble_id].model_dump(mode="json")
                for bubble in page.bubbles
                if bubble.bubble_id in translation_by_id
            ]
            files_written.append(
                store.write_translations(
                    page.page_id,
                    {
                        "page_id": page.page_id,
                        "page_index": page.page_index,
                        "bubbles": bubbles,
                        "translations": page_translations,
                    },
                )
            )
        return files_written

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

    def _write_report_output(
        self,
        output_dir: Path,
        ctx: PipelineContext,
        cfg: ProjectConfig,
    ) -> Path:
        from mga.artifacts.translation_report import build_translation_report

        requested_output = Path(ctx.metadata.get("output_path", cfg.output_dir or "report.json"))
        report_path = (
            requested_output
            if requested_output.suffix.lower() == ".json"
            else output_dir / "report.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = build_translation_report(ctx)
        payload = {
            "entries": [asdict(entry) for entry in report.entries],
            "summary": report.summary,
        }
        report_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return report_path

    def _repack_to_format(
        self, output_dir: Path, ctx: PipelineContext, cfg: ProjectConfig, output_format: str
    ) -> None:
        """Convert rendered page images into the target format (pdf, epub, cbz, etc.)."""
        import logging
        logger = logging.getLogger(__name__)

        rendered_images = sorted(output_dir.glob("page-*.png"))
        if not rendered_images:
            logger.warning(f"No rendered page images found in {output_dir}, skipping format conversion")
            return

        from mga.format import get_adapter
        from mga.models.format import TranslatedPage

        try:
            adapter = get_adapter(output_format)
        except ValueError as e:
            logger.error(f"Format conversion failed: {e}")
            return

        original_by_index = {
            page.page_index: page.image.path
            for page in ctx.pages
            if page.image and page.image.path
        }
        pages = []
        for i, img in enumerate(rendered_images):
            page_json = {"source": "rendered"}
            if output_format == "bilingual" and i in original_by_index:
                page_json["original_image_path"] = str(original_by_index[i])
            pages.append(
                TranslatedPage(
                    index=i,
                    image_path=str(img),
                    page_json=page_json,
                )
            )

        extension = "pdf" if output_format == "bilingual" else output_format
        output_file = output_dir / f"output.{extension}"
        adapter.repack(iter(pages), output_file)
        logger.info(f"Format conversion complete: {output_file}")
