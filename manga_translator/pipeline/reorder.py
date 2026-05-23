from __future__ import annotations

from dataclasses import replace
from typing import List

from ..utils import sort_regions
from .contract import PostOCRArtifact, RegionOrderEntry


def reorder_artifact(
    artifact: PostOCRArtifact,
    *,
    right_to_left: bool,
    img,
    force_simple_sort: bool = False,
    source: str = "runtime-default",
) -> PostOCRArtifact:
    sorted_regions = sort_regions(
        list(artifact.text_regions),
        right_to_left=right_to_left,
        img=img,
        force_simple_sort=force_simple_sort,
    )

    original_positions = {id(region): index for index, region in enumerate(artifact.text_regions)}
    order: List[RegionOrderEntry] = []
    for reading_index, region in enumerate(sorted_regions):
        original_index = original_positions[id(region)]
        base_entry = artifact.order[original_index]
        order.append(
            replace(
                base_entry,
                reading_index=reading_index,
                text=region.text,
            )
        )

    return PostOCRArtifact(
        ocr_lines=list(artifact.ocr_lines),
        text_regions=sorted_regions,
        order=order,
        source=source,
    )
