import numpy as np

from manga_translator.pipeline import build_post_ocr_artifact, reorder_artifact
from manga_translator.utils import Quadrilateral, TextBlock


def _quad(x1: int, y1: int, x2: int, y2: int, text: str) -> Quadrilateral:
    pts = np.array([
        [x1, y1],
        [x2, y1],
        [x2, y2],
        [x1, y2],
    ])
    return Quadrilateral(pts, text, 1.0)


def _region(line: Quadrilateral) -> TextBlock:
    return TextBlock([line.pts], [line.text], font_size=line.font_size)


def test_build_post_ocr_artifact_tracks_line_membership():
    line_a = _quad(10, 10, 30, 30, "A")
    line_b = _quad(60, 10, 80, 30, "B")
    region_a = _region(line_a)
    region_b = _region(line_b)

    artifact = build_post_ocr_artifact([line_a, line_b], [region_a, region_b], source="test")

    assert artifact.source == "test"
    assert [entry.original_index for entry in artifact.order] == [0, 1]
    assert artifact.order[0].line_indices == [0]
    assert artifact.order[1].line_indices == [1]
    assert artifact.reordered_texts == ["A", "B"]


def test_reorder_artifact_sorts_regions_left_to_right():
    line_left = _quad(10, 10, 30, 30, "left")
    line_right = _quad(80, 10, 100, 30, "right")
    region_right = _region(line_right)
    region_left = _region(line_left)

    artifact = build_post_ocr_artifact(
        [line_right, line_left],
        [region_right, region_left],
        source="unsorted",
    )

    reordered = reorder_artifact(
        artifact,
        right_to_left=False,
        img=None,
        force_simple_sort=True,
        source="sorted",
    )

    assert reordered.source == "sorted"
    assert [region.text for region in reordered.text_regions] == ["left", "right"]
    assert [entry.original_index for entry in reordered.order] == [1, 0]
    assert [entry.reading_index for entry in reordered.order] == [0, 1]
    assert reordered.reordered_texts == ["left", "right"]


def test_reorder_artifact_sorts_regions_right_to_left():
    line_left = _quad(10, 10, 30, 30, "left")
    line_right = _quad(80, 10, 100, 30, "right")
    region_left = _region(line_left)
    region_right = _region(line_right)

    artifact = build_post_ocr_artifact(
        [line_left, line_right],
        [region_left, region_right],
        source="unsorted",
    )

    reordered = reorder_artifact(
        artifact,
        right_to_left=True,
        img=None,
        force_simple_sort=True,
        source="rtl",
    )

    assert [region.text for region in reordered.text_regions] == ["right", "left"]
    assert [entry.original_index for entry in reordered.order] == [1, 0]
    assert reordered.reordered_texts == ["right", "left"]
