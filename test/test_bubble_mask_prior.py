import cv2
import numpy as np

from manga_translator.mask_refinement import (
    _extract_elliptic_bubble_mask_local,
    _group_text_boxes,
    _merge_bubble_mask_prior,
)
from manga_translator.utils import TextBlock


def _block(x: int, y: int, w: int, h: int, text: str = "text") -> TextBlock:
    return TextBlock(
        [np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype=np.int32)],
        [text],
    )


def _rect_mask(shape: tuple[int, int], *boxes: tuple[int, int, int, int]) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    for x, y, w, h in boxes:
        mask[y:y + h, x:x + w] = 255
    return mask


def test_multi_text_one_bubble_expands_to_shared_interior_without_frame():
    image = np.full((180, 260, 3), 255, dtype=np.uint8)
    cv2.ellipse(image, (130, 90), (82, 48), 0, 0, 360, (0, 0, 0), 5)

    boxes = [(94, 74, 34, 18), (134, 94, 32, 18)]
    regions = [_block(*box) for box in boxes]
    final_mask = _rect_mask(image.shape[:2], *boxes)

    expanded = _merge_bubble_mask_prior(
        final_mask,
        regions,
        image,
        mode="expand_text",
        enabled=True,
        enlarge_ratio=5.0,
        min_area_ratio=0.1,
        max_area_ratio=30.0,
    )

    assert len(_group_text_boxes(regions)) == 1
    assert expanded[90, 130] == 255
    assert np.count_nonzero(expanded) > np.count_nonzero(final_mask) * 4
    assert expanded[90, 48] == 0
    assert expanded[90, 212] == 0


def test_two_bubbles_stay_separate_without_bridge():
    image = np.full((180, 280, 3), 255, dtype=np.uint8)
    cv2.ellipse(image, (80, 90), (48, 34), 0, 0, 360, (0, 0, 0), 5)
    cv2.ellipse(image, (194, 90), (48, 34), 0, 0, 360, (0, 0, 0), 5)

    boxes = [(66, 81, 28, 18), (180, 81, 28, 18)]
    regions = [_block(*box) for box in boxes]
    final_mask = _rect_mask(image.shape[:2], *boxes)

    expanded = _merge_bubble_mask_prior(
        final_mask,
        regions,
        image,
        mode="expand_text",
        enabled=True,
        enlarge_ratio=5.0,
        min_area_ratio=0.1,
        max_area_ratio=30.0,
    )

    assert len(_group_text_boxes(regions)) == 2
    assert expanded[90, 80] == 255
    assert expanded[90, 194] == 255
    assert expanded[90, 137] == 0


def test_axis_freeze_allows_vertical_growth_after_horizontal_boundary():
    image = np.full((240, 200, 3), 255, dtype=np.uint8)
    cv2.ellipse(image, (100, 120), (42, 86), 0, 0, 360, (0, 0, 0), 5)
    box = (74, 108, 52, 24)

    local_mask, rect = _extract_elliptic_bubble_mask_local(
        image,
        *box,
        text_mask_local=_rect_mask((box[3], box[2]), (0, 0, box[2], box[3])),
        enlarge_ratio=6.0,
    )

    assert local_mask is not None
    assert rect is not None
    x1, y1, _, _ = rect
    assert local_mask[46 - y1, 100 - x1] == 255
    assert local_mask[194 - y1, 100 - x1] == 255
    assert local_mask[120 - y1, 56 - x1] == 0
    assert local_mask[120 - y1, 144 - x1] == 0


def test_text_like_strokes_inside_bubble_do_not_stop_expansion():
    image = np.full((180, 260, 3), 255, dtype=np.uint8)
    cv2.ellipse(image, (130, 90), (82, 48), 0, 0, 360, (0, 0, 0), 5)
    cv2.line(image, (122, 58), (122, 122), (0, 0, 0), 2)
    cv2.line(image, (138, 58), (138, 122), (0, 0, 0), 2)
    box = (108, 78, 44, 24)

    local_mask, rect = _extract_elliptic_bubble_mask_local(
        image,
        *box,
        text_mask_local=_rect_mask((box[3], box[2]), (0, 0, box[2], box[3])),
        enlarge_ratio=6.0,
    )

    assert local_mask is not None
    assert rect is not None
    x1, y1, _, _ = rect
    assert local_mask[90 - y1, 130 - x1] == 255
    assert local_mask[90 - y1, 92 - x1] == 255
    assert local_mask[90 - y1, 168 - x1] == 255


def test_small_ruby_like_glyphs_near_text_do_not_become_frame_boundary():
    image = np.full((190, 280, 3), 255, dtype=np.uint8)
    cv2.ellipse(image, (140, 96), (86, 50), 0, 0, 360, (0, 0, 0), 5)

    # Main OCR box misses small ruby-like glyphs to the right. These strokes are
    # dark and near the text, but they should be erased, not treated as a frame.
    box = (112, 79, 42, 30)
    for x, y, ch in [(160, 77, 7), (171, 84, 6), (162, 98, 8), (174, 107, 6)]:
        cv2.line(image, (x, y), (x + 3, y + ch), (0, 0, 0), 2)
        cv2.line(image, (x + 5, y + 1), (x + 8, y + ch - 1), (0, 0, 0), 1)

    local_mask, rect = _extract_elliptic_bubble_mask_local(
        image,
        *box,
        text_mask_local=_rect_mask((box[3], box[2]), (0, 0, box[2], box[3])),
        enlarge_ratio=6.0,
    )

    assert local_mask is not None
    assert rect is not None
    x1, y1, _, _ = rect
    assert local_mask[96 - y1, 168 - x1] == 255
    assert local_mask[96 - y1, 188 - x1] == 255
    assert local_mask[96 - y1, 222 - x1] == 0


def test_fallback_borderless_area_keeps_required_text_and_does_not_flood_page():
    image = np.full((180, 260, 3), 255, dtype=np.uint8)
    box = (110, 80, 40, 22)
    final_mask = _rect_mask(image.shape[:2], box)
    region = _block(*box)

    expanded = _merge_bubble_mask_prior(
        final_mask,
        [region],
        image,
        mode="expand_text",
        enabled=True,
        enlarge_ratio=6.0,
        min_area_ratio=0.1,
        max_area_ratio=30.0,
    )

    assert np.all(expanded[80:102, 110:150] == 255)
    assert np.count_nonzero(expanded) < image.shape[0] * image.shape[1] * 0.2
