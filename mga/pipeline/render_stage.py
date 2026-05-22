"""Stage 6 -- Rendering via external runtime (two-pass mode)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from mga.models import ProjectConfig

from .stages import PipelineContext, PipelineStage

logger = logging.getLogger(__name__)


class RenderStage(PipelineStage):
    """Invoke the external runtime in render-only mode.

    When a payload directory is available (from Pass 1 export), this stage:
    1. Writes translations.json with mga's translation output
    2. Calls the runtime with --render-only to produce final images

    When no payload directory is available, rendering is skipped (artifact-only mode).
    """

    @property
    def name(self) -> str:
        return "render"

    @property
    def order(self) -> int:
        return 60

    def execute(self, context: PipelineContext) -> PipelineContext:
        cfg: ProjectConfig = context.project_config
        payload_dir = context.metadata.get("artifact_payload_dir")

        if not payload_dir:
            context.artifacts[self.name] = {
                "mode": "skipped",
                "note": "No payload directory — rendering requires two-pass mode with external runtime",
            }
            return context

        payload_path = Path(payload_dir)
        output_dir = Path(cfg.output_dir) if cfg.output_dir else Path("output")

        self._write_translations_json(payload_path, context, cfg)

        try:
            from mga.runtime_bridge.external import run_render_only
            result = run_render_only(
                payload_dir=payload_path,
                output_dir=output_dir,
            )
            context.artifacts[self.name] = {
                "mode": "render-only",
                "rendered_images": result.get("rendered_images", []),
                "output_dir": str(output_dir),
            }
        except Exception as e:
            logger.error(f"Render-only failed: {e}")
            context.artifacts[self.name] = {
                "mode": "render-only",
                "error": str(e),
            }
            context.errors.append({"stage": self.name, "error": str(e)})

        return context

    def _write_translations_json(
        self, payload_path: Path, context: PipelineContext, cfg: ProjectConfig
    ) -> None:
        """Write mga translations in the format the runtime expects."""
        translations = []
        for t in context.translations:
            if not t.bubble_id.startswith("region-"):
                continue
            try:
                idx = int(t.bubble_id.split("-")[1])
            except (IndexError, ValueError):
                continue
            translations.append({
                "region_index": idx,
                "translation": t.text,
                "target_lang": cfg.target_lang or "CHS",
            })

        payload = {
            "version": 1,
            "target_lang": cfg.target_lang or "CHS",
            "translations": translations,
        }
        (payload_path / "translations.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
