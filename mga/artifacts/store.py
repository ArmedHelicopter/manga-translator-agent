"""Artifact persistence for Phase 1 runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel


class ArtifactStore:
    """Centralized artifact path management and persistence."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.pages_dir = self.root / "pages"
        self.translations_dir = self.root / "translations"
        self.renders_dir = self.root / "renders"
        self.debug_dir = self.root / "debug"
        self.root.mkdir(parents=True, exist_ok=True)
        self.pages_dir.mkdir(exist_ok=True)
        self.translations_dir.mkdir(exist_ok=True)
        self.renders_dir.mkdir(exist_ok=True)
        self.debug_dir.mkdir(exist_ok=True)

    def _normalize(self, payload: Any) -> Any:
        if isinstance(payload, BaseModel):
            return payload.model_dump(mode="json")
        if isinstance(payload, list):
            return [self._normalize(item) for item in payload]
        if isinstance(payload, dict):
            return {key: self._normalize(value) for key, value in payload.items()}
        return payload

    def write_json(self, relative_path: str, payload: Any) -> str:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self._normalize(payload), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return str(path.relative_to(self.root))

    def write_page(self, page_id: str, payload: Any) -> str:
        return self.write_json(f"pages/{page_id}.json", payload)

    def write_translations(self, page_id: str, payload: Any) -> str:
        return self.write_json(f"translations/{page_id}.json", payload)

    def write_render(self, filename: str, image: Image.Image) -> str:
        path = self.renders_dir / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(path)
        return str(path.relative_to(self.root))

    def write_debug_text(self, relative_path: str, content: str) -> str:
        path = self.debug_dir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return str(path.relative_to(self.root))

    def write_run_summary(self, payload: Any) -> str:
        """Write run.json summary."""
        return self.write_json("run.json", payload)

    def write_qa_report(self, payload: Any) -> str:
        """Write qa_report.json."""
        return self.write_json("qa_report.json", payload)

    def write_translation_report(self, payload: Any) -> str:
        """Write translation-report.json."""
        return self.write_json("translation-report.json", payload)
