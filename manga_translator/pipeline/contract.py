from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

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
