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
            from mga.runtime_bridge.external import run_render_only
            result = run_render_only(
                payload_dir=payload_path,
                output_dir=output_dir,
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
        for t in context.translations:
            if not t.bubble_id.startswith(prefix):
                continue
            try:
                region_idx = int(t.bubble_id.split("-")[2])
            except (IndexError, ValueError):
                continue
            translations.append({
                "region_index": region_idx,
                "translation": self._extract_render_text(t.text),
                "target_lang": _normalize_runtime_lang_code(cfg.target_lang or "CHS"),
            })
            for fn in t.footnotes:
                original = self._sanitize_footnote_text(fn.original)
                translation = self._sanitize_footnote_text(fn.translation)
                if not original or not translation:
                    continue
                if fn.type not in {"loanword", "sfx", "visual"}:
                    continue
                key = (original, translation)
                if key in seen_footnote_keys:
                    continue
                seen_footnote_keys.add(key)
                footnotes.append({
                    "original": original,
                    "translation": translation,
                    "type": fn.type,
                })

            # Name footnotes are intentionally disabled by product rule.

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
