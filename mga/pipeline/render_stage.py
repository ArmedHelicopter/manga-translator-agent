"""Stage 6 -- Rendering via external runtime (two-pass mode)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from mga.models import ProjectConfig
from manga_translator.pipeline.contract import _normalize_runtime_lang_code

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

        # Check for multi-page manifest
        pages_manifest = payload_path / "pages.json"
        if pages_manifest.exists():
            import json as _json
            pages_list = _json.loads(pages_manifest.read_text(encoding="utf-8"))
        else:
            pages_list = [{"page_index": 0}]

        # Write per-page translation files
        for page_entry in pages_list:
            self._write_page_translations(payload_path, context, cfg, page_entry["page_index"])

        # Single subprocess call renders all pages
        try:
            renderer_plugin = self._renderer_plugin_config(cfg)
            if renderer_plugin:
                from mga.plugins import instantiate_plugin_from_config

                renderer = instantiate_plugin_from_config(renderer_plugin)
                if not hasattr(renderer, "render"):
                    raise TypeError("Renderer plugin must define a render(context, payload_dir, output_dir) method.")
                plugin_result = renderer.render(
                    context=context,
                    payload_dir=payload_path,
                    output_dir=output_dir,
                )
                if plugin_result is None:
                    plugin_result = {}
                if not isinstance(plugin_result, dict):
                    raise TypeError("Renderer plugin render() must return a dict or None.")
                context.artifacts[self.name] = {
                    "mode": "plugin-renderer",
                    "output_dir": str(output_dir),
                    "pages_rendered": len(pages_list),
                    "plugin": renderer_plugin.get("class") or renderer_plugin.get("class_path") or renderer_plugin.get("plugin"),
                    **plugin_result,
                }
                return context

            from mga.runtime_bridge.external import run_render_only
            result = run_render_only(
                payload_dir=payload_path,
                output_dir=output_dir,
                inpaint_backend=getattr(cfg, "inpaint_backend", "auto"),
            )
            context.artifacts[self.name] = {
                "mode": "render-only",
                "rendered_images": result.get("rendered_images", []),
                "output_dir": str(output_dir),
                "pages_rendered": len(pages_list),
            }
        except Exception as e:
            logger.error(f"Render-only failed: {e}")
            context.artifacts[self.name] = {
                "mode": "render-only",
                "error": str(e),
            }
            context.errors.append({"stage": self.name, "error": str(e)})

        return context

    @staticmethod
    def _renderer_plugin_config(cfg: ProjectConfig) -> dict | None:
        plugins = cfg.plugins or {}
        renderer = plugins.get("renderer")
        if isinstance(renderer, dict) and renderer:
            return renderer
        renderers = plugins.get("renderers")
        if isinstance(renderers, dict):
            default_renderer = renderers.get("default") or renderers.get("primary")
            if isinstance(default_renderer, dict) and default_renderer:
                return default_renderer
        return None

    def _write_page_translations(
        self, payload_path: Path, context: PipelineContext, cfg: ProjectConfig, page_idx: int
    ) -> None:
        """Write translations for a specific page, including footnotes."""
        prefix = f"region-{page_idx:04d}-"
        source_by_bubble = {
            bubble.bubble_id: bubble.source_text
            for page in context.pages
            for bubble in page.bubbles
            if bubble.bubble_id.startswith(prefix)
        }
        translations = []
        footnotes = []
        seen_footnote_keys: set[tuple[str, str]] = set()

        # S2T converter (cached per stage — instantiated once per RenderStage.execute call).
        # Converts rendered text from simplified to traditional Chinese when
        # cfg.chinese_variant is set. "auto" disables conversion.
        s2t_converter = self._get_s2t_converter(cfg)

        for t in context.translations:
            if not t.bubble_id.startswith(prefix):
                continue
            try:
                region_idx = int(t.bubble_id.split("-")[2])
            except (IndexError, ValueError):
                continue
            render_text = self._extract_render_text(t.text)
            if s2t_converter is not None:
                render_text = s2t_converter.convert(render_text)
            translations.append({
                "region_index": region_idx,
                "translation": render_text,
                "target_lang": _normalize_runtime_lang_code(cfg.target_lang or "CHS"),
            })

            # Name footnotes are intentionally disabled by product rule.

        # Term footnotes: prefer the page-level compiled set (deduplicated,
        # database-enriched explanations, all explanatory types). Fall back to
        # bubble-level candidates when compilation has not run.
        page_obj = next(
            (p for p in context.pages if p.page_index == page_idx),
            None,
        )
        compiled = list(getattr(page_obj, "page_footnotes", []) or []) if page_obj else []
        if compiled:
            for fn in compiled:
                original = self._sanitize_footnote_text(fn.term)
                translation = self._sanitize_footnote_text(fn.translation)
                if not original or not translation:
                    continue
                key = (original, translation)
                if key in seen_footnote_keys:
                    continue
                seen_footnote_keys.add(key)
                footnotes.append({
                    "original": original,
                    "translation": translation,
                    "type": fn.type,
                    "explanation": self._sanitize_footnote_text(fn.explanation),
                })
        else:
            for t in context.translations:
                if not t.bubble_id.startswith(prefix):
                    continue
                for fn in t.footnotes:
                    original = self._sanitize_footnote_text(fn.original)
                    translation = self._sanitize_footnote_text(fn.translation)
                    if not original or not translation:
                        continue
                    if fn.type not in {"loanword", "sfx", "visual", "cultural", "coined", "fictional"}:
                        continue
                    key = (original, translation)
                    if key in seen_footnote_keys:
                        continue
                    seen_footnote_keys.add(key)
                    footnotes.append({
                        "original": original,
                        "translation": translation,
                        "type": fn.type,
                        "explanation": self._sanitize_footnote_text(fn.explanation or ""),
                    })

        for page in context.pages:
            if page.page_index != page_idx:
                continue
            for fn in getattr(page, "visual_footnotes", []):
                original = self._sanitize_footnote_text(fn.source_text)
                translation = self._sanitize_footnote_text(fn.translation_hint or fn.notes or "见图中文字")
                if not original:
                    continue
                key = (original, translation)
                if key in seen_footnote_keys:
                    continue
                seen_footnote_keys.add(key)
                footnotes.append({
                    "original": original,
                    "translation": translation,
                    "type": "visual",
                    "kind": fn.kind,
                })

        payload = {
            "version": 1,
            "target_lang": _normalize_runtime_lang_code(cfg.target_lang or "CHS"),
            "translations": translations,
            "footnotes": footnotes,
        }
        suffix = f"-{page_idx:04d}"
        (payload_path / f"translations{suffix}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _extract_render_text(raw_text: str) -> str:
        """Extract translatable text from plain text or JSON-like model output."""
        text = (raw_text or "").strip()
        if not text:
            return text

        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                text = "\n".join(lines[1:-1]).strip()

        parsed = None
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
            except Exception:
                parsed = None
        else:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    parsed = json.loads(text[start : end + 1])
                except Exception:
                    parsed = None

        if isinstance(parsed, dict):
            extracted = parsed.get("text") or parsed.get("translation")
            if isinstance(extracted, str) and extracted.strip():
                return RenderStage._strip_inline_footnote_noise(extracted.strip())

        # Fallback: extract text field from malformed JSON-like output.
        m = re.search(r'"text"\s*:\s*"((?:\\.|[^"\\])*)"', text, flags=re.DOTALL)
        if m:
            try:
                extracted = json.loads(f'"{m.group(1)}"')
                if isinstance(extracted, str) and extracted.strip():
                    return RenderStage._strip_inline_footnote_noise(extracted.strip())
            except Exception:
                pass

        text = RenderStage._strip_json_noise(text)
        return RenderStage._strip_inline_footnote_noise(text)

    @staticmethod
    def _strip_inline_footnote_noise(text: str) -> str:
        """Remove common inline footnote tails from bubble text.

        Footnotes should be rendered only by dedicated footnote overlay.
        """
        s = (text or "").strip()
        if not s:
            return s
        # Remove trailing bracket notes like "（xx）"/"(xx)" often used as inline footnotes.
        s = re.sub(r"[（(][^)）]{1,24}[)）]\s*$", "", s).strip()
        # Remove explicit footnote label tails, e.g. "※ xxx"
        s = re.sub(r"\s*※\s*.*$", "", s).strip()
        return s

    @staticmethod
    def _strip_json_noise(text: str) -> str:
        """Strip obvious JSON scaffolding that should never be rendered in bubble text."""
        s = (text or "").strip()
        if not s:
            return s
        # Remove known JSON keys if they leak as plain text.
        s = re.sub(r'"(?:footnotes|rationale|confidence|original|translation|type)"\s*:\s*', "", s)
        # Remove leftover braces/brackets that usually come from JSON blobs.
        s = re.sub(r"[{}\[\]]", "", s)
        # Remove markdown-fence tag remnants.
        s = s.replace("json", "").replace("```", "")
        return s.strip()

    @staticmethod
    def _sanitize_footnote_text(text: str) -> str:
        """Keep footnote fields human-readable and JSON-free."""
        s = (text or "").strip()
        if not s:
            return s
        if s.startswith("```"):
            lines = s.splitlines()
            if len(lines) >= 3 and lines[-1].strip() == "```":
                s = "\n".join(lines[1:-1]).strip()
        # Try to extract from malformed key-value form.
        m = re.search(r'"(?:text|translation|original)"\s*:\s*"((?:\\.|[^"\\])*)"', s, flags=re.DOTALL)
        if m:
            try:
                s = json.loads(f'"{m.group(1)}"')
            except Exception:
                pass
        s = RenderStage._strip_json_noise(s)
        return s.strip()

    @staticmethod
    def _get_s2t_converter(cfg: ProjectConfig):
        """Get a cached S2T converter for the configured Chinese variant.

        Returns None if variant is "auto" (no conversion).
        The converter is cached on the instance for the stage's lifetime.
        """
        variant = getattr(cfg, "chinese_variant", "auto") or "auto"
        if variant in ("auto", "", None):
            return None
        if not hasattr(RenderStage, "_s2t_converter_cache"):
            RenderStage._s2t_converter_cache = {}
        cache_key = variant
        if cache_key not in RenderStage._s2t_converter_cache:
            try:
                from mga.cultural.s2t_converter import S2TConverter
                RenderStage._s2t_converter_cache[cache_key] = S2TConverter(variant)
            except ImportError:
                RenderStage._s2t_converter_cache[cache_key] = None
        return RenderStage._s2t_converter_cache.get(cache_key)

