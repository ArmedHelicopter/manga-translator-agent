from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence

import cv2
import numpy as np

from ..utils import Quadrilateral, TextBlock


@dataclass(frozen=True)
class OCRLineSnapshot:
    index: int
    text: str
    direction: str
    confidence: float
    points: np.ndarray

    @classmethod
    def from_textline(cls, index: int, textline: Quadrilateral) -> "OCRLineSnapshot":
        return cls(
            index=index,
            text=textline.text,
            direction=textline.direction,
            confidence=textline.prob,
            points=np.array(textline.pts, copy=True),
        )


@dataclass(frozen=True)
class RegionOrderEntry:
    original_index: int
    reading_index: int
    text: str
    line_indices: List[int]
    xyxy: np.ndarray


@dataclass(frozen=True)
class PostOCRArtifact:
    ocr_lines: List[OCRLineSnapshot]
    text_regions: List[TextBlock]
    order: List[RegionOrderEntry]
    source: str = "runtime-default"

    @property
    def reordered_texts(self) -> List[str]:
        ordered = sorted(self.order, key=lambda entry: entry.reading_index)
        return [entry.text for entry in ordered]


def _region_line_indices(region: TextBlock, ocr_lines: Sequence[Quadrilateral]) -> List[int]:
    indices: List[int] = []
    for line_index, textline in enumerate(ocr_lines):
        for region_line in region.lines:
            if np.array_equal(region_line, textline.pts):
                indices.append(line_index)
                break
    return indices


def build_post_ocr_artifact(
    ocr_lines: Sequence[Quadrilateral],
    text_regions: Sequence[TextBlock],
    source: str = "runtime-default",
) -> PostOCRArtifact:
    line_snapshots = [
        OCRLineSnapshot.from_textline(index, textline)
        for index, textline in enumerate(ocr_lines)
    ]

    order = [
        RegionOrderEntry(
            original_index=index,
            reading_index=index,
            text=region.text,
            line_indices=_region_line_indices(region, ocr_lines),
            xyxy=np.array(region.xyxy, copy=True),
        )
        for index, region in enumerate(text_regions)
    ]

    return PostOCRArtifact(
        ocr_lines=line_snapshots,
        text_regions=list(text_regions),
        order=order,
        source=source,
    )


def _textblock_to_dict(region: TextBlock, index: int) -> Dict[str, Any]:
    return {
        "index": index,
        "text": region.text,
        "texts": region.texts,
        "lines": region.lines.tolist(),
        "font_size": int(region.font_size),
        "angle": float(region.angle),
        "direction": region._direction,
        "alignment": region._alignment,
        "fg_color": list(region.fg_colors) if hasattr(region, 'fg_colors') else [0, 0, 0],
        "bg_color": list(region.bg_colors) if hasattr(region, 'bg_colors') else [255, 255, 255],
        "source_lang": getattr(region, '_source_lang', ''),
        "target_lang": region.target_lang,
        "line_spacing": region.line_spacing,
        "letter_spacing": region.letter_spacing,
        "bold": region.bold,
        "italic": region.italic,
        "font_weight": region.font_weight,
        "default_stroke_width": region.default_stroke_width,
        "prob": region.prob,
    }


def _dict_to_textblock(d: Dict[str, Any]) -> TextBlock:
    return TextBlock(
        lines=d["lines"],
        texts=d.get("texts") or [d["text"]],
        font_size=d.get("font_size", -1),
        angle=d.get("angle", 0.0),
        direction=d.get("direction", "auto"),
        alignment=d.get("alignment", "auto"),
        fg_color=tuple(d.get("fg_color", (0, 0, 0))),
        bg_color=tuple(d.get("bg_color", (255, 255, 255))),
        source_lang=d.get("source_lang", ""),
        target_lang=d.get("target_lang", ""),
        line_spacing=d.get("line_spacing", 1.0),
        letter_spacing=d.get("letter_spacing", 1.0),
        bold=d.get("bold", False),
        italic=d.get("italic", False),
        font_weight=d.get("font_weight", 50),
        default_stroke_width=d.get("default_stroke_width", 0.2),
        prob=d.get("prob", 1.0),
    )


def serialize_render_payload(ctx, config, payload_dir: str) -> None:
    """Export text regions + inpainted image + render config to a payload directory.

    Called after inpainting completes, before rendering. Enables a two-pass
    workflow where mga injects translations between passes.
    """
    payload_path = Path(payload_dir)
    payload_path.mkdir(parents=True, exist_ok=True)

    regions_data = [
        _textblock_to_dict(region, i)
        for i, region in enumerate(ctx.text_regions)
    ]

    render_config = {
        "renderer": str(getattr(config.render, 'renderer', 'default')),
        "font_size": getattr(config.render, 'font_size', None),
        "font_size_offset": getattr(config.render, 'font_size_offset', 0),
        "font_size_minimum": getattr(config.render, 'font_size_minimum', -1),
        "no_hyphenation": getattr(config.render, 'no_hyphenation', False),
        "line_spacing": getattr(config.render, 'line_spacing', None),
    }

    h, w = ctx.img_inpainted.shape[:2]
    c = ctx.img_inpainted.shape[2] if len(ctx.img_inpainted.shape) > 2 else 1

    artifact = {
        "version": 1,
        "text_regions": regions_data,
        "render_config": render_config,
        "image_shape": [h, w, c],
    }

    (payload_path / "artifact.json").write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    cv2.imwrite(
        str(payload_path / "inpainted.png"),
        cv2.cvtColor(ctx.img_inpainted, cv2.COLOR_RGB2BGR),
    )

    if ctx.mask is not None:
        cv2.imwrite(str(payload_path / "mask.png"), ctx.mask)


def deserialize_render_payload(payload_dir: str):
    """Load text regions + inpainted image + render config from a payload directory.

    Returns (text_regions, img_inpainted, mask_or_none, render_config).
    """
    payload_path = Path(payload_dir)

    artifact_data = json.loads(
        (payload_path / "artifact.json").read_text(encoding="utf-8")
    )

    text_regions = [
        _dict_to_textblock(d) for d in artifact_data["text_regions"]
    ]

    img_bgr = cv2.imread(str(payload_path / "inpainted.png"))
    img_inpainted = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    mask = None
    mask_path = payload_path / "mask.png"
    if mask_path.exists():
        mask = cv2.imread(str(mask_path), cv2.IMREAD_GRAYSCALE)

    return text_regions, img_inpainted, mask, artifact_data.get("render_config", {})


def load_translations(payload_dir: str) -> List[Dict[str, Any]]:
    """Load mga translations from translations.json in the payload directory."""
    payload_path = Path(payload_dir)
    translations_path = payload_path / "translations.json"
    if not translations_path.exists():
        return []
    data = json.loads(translations_path.read_text(encoding="utf-8"))
    return data.get("translations", [])
