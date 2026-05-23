from dataclasses import dataclass
from typing import List

import cv2
import numpy as np

from .text_mask_utils import complete_mask_fill, complete_mask
from ..utils import TextBlock, Quadrilateral
from ..utils.bubble import is_ignore


@dataclass(frozen=True)
class _TextGroup:
    bbox: tuple[int, int, int, int]
    boxes: list[tuple[int, int, int, int]]


def _fill_holes(mask: np.ndarray) -> np.ndarray:
    if mask is None or mask.size == 0:
        return mask
    h, w = mask.shape[:2]
    flood = mask.copy()
    ff = np.zeros((h + 2, w + 2), dtype=np.uint8)
    cv2.floodFill(flood, ff, (0, 0), 255)
    holes = cv2.bitwise_not(flood)
    return cv2.bitwise_or(mask, holes)


def _dark_line_mask(crop: np.ndarray) -> np.ndarray:
    if crop.size == 0:
        return np.zeros(crop.shape[:2], dtype=np.uint8)

    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, dark = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return cv2.morphologyEx(
        dark,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=1,
    )


def _inside_bubble_without_border(crop: np.ndarray, bubble_mask: np.ndarray) -> np.ndarray:
    if crop.size == 0 or bubble_mask.size == 0:
        return bubble_mask

    local_bin = (bubble_mask > 0).astype(np.uint8) * 255
    border_guard = cv2.dilate(
        _dark_line_mask(crop),
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
        iterations=1,
    )
    interior = cv2.bitwise_and(local_bin, cv2.bitwise_not(border_guard))
    interior = cv2.erode(
        interior,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=1,
    )
    if np.count_nonzero(interior) == 0:
        return local_bin
    return interior


def _text_mask_bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    ys, xs = np.where(mask > 0)
    if xs.size == 0 or ys.size == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _bbox_union(boxes: list[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    x1 = min(x for x, _, _, _ in boxes)
    y1 = min(y for _, y, _, _ in boxes)
    x2 = max(x + w for x, _, w, _ in boxes)
    y2 = max(y + h for _, y, _, h in boxes)
    return x1, y1, x2 - x1, y2 - y1


def _expanded_rect(box: tuple[int, int, int, int]) -> tuple[float, float, float, float]:
    x, y, w, h = box
    pad_x = max(8.0, float(w) * 0.75)
    pad_y = max(8.0, float(h) * 1.25)
    return x - pad_x, y - pad_y, x + w + pad_x, y + h + pad_y


def _rects_overlap(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    return min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])


def _group_text_boxes(text_regions: List[TextBlock]) -> list[_TextGroup]:
    boxes: list[tuple[int, int, int, int]] = []
    for region in text_regions:
        try:
            x, y, w, h = np.asarray(region.xywh, dtype=np.int32).tolist()
        except Exception:
            continue
        if w > 2 and h > 2:
            boxes.append((int(x), int(y), int(w), int(h)))

    if not boxes:
        return []

    parent = list(range(len(boxes)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    expanded = [_expanded_rect(box) for box in boxes]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            if _rects_overlap(expanded[i], expanded[j]):
                union(i, j)

    groups: dict[int, list[tuple[int, int, int, int]]] = {}
    for idx, box in enumerate(boxes):
        groups.setdefault(find(idx), []).append(box)
    return [_TextGroup(_bbox_union(group_boxes), group_boxes) for group_boxes in groups.values()]


def _region_window(
    image_shape: tuple[int, int],
    rx: int,
    ry: int,
    rw: int,
    rh: int,
    enlarge_ratio: float,
) -> tuple[int, int, int, int]:
    h_img, w_img = image_shape[:2]
    ratio = max(float(enlarge_ratio), 1.0)
    base = max(rw, rh)
    pad_x = max(8, int(round(base * (ratio - 1.0) * 0.5)))
    pad_y = max(8, int(round(base * (ratio - 1.0) * 0.5)))
    x1 = max(0, rx - pad_x)
    y1 = max(0, ry - pad_y)
    x2 = min(w_img, rx + rw + pad_x)
    y2 = min(h_img, ry + rh + pad_y)
    return x1, y1, x2, y2


def _ellipse_mask(shape: tuple[int, int], center: tuple[int, int], axes: tuple[int, int]) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    cv2.ellipse(mask, center, (max(1, int(axes[0])), max(1, int(axes[1]))), 0, 0, 360, 255, -1)
    return mask


def _required_text_mask(shape: tuple[int, int], bbox: tuple[int, int, int, int]) -> np.ndarray:
    x1, y1, x2, y2 = bbox
    margin = max(2, int(round(min(max(1, x2 - x1), max(1, y2 - y1)) * 0.08)))
    mask = np.zeros(shape, dtype=np.uint8)
    mask[max(0, y1 - margin):min(shape[0], y2 + margin), max(0, x1 - margin):min(shape[1], x2 + margin)] = 255
    return mask


def _required_text_mask_from_boxes(
    shape: tuple[int, int],
    boxes: list[tuple[int, int, int, int]],
) -> np.ndarray:
    mask = np.zeros(shape, dtype=np.uint8)
    for x, y, w, h in boxes:
        margin = max(2, int(round(min(max(1, w), max(1, h)) * 0.08)))
        x1 = max(0, x - margin)
        y1 = max(0, y - margin)
        x2 = min(shape[1], x + w + margin)
        y2 = min(shape[0], y + h + margin)
        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = 255
    return mask


def _component_bbox_inside(
    x: int,
    y: int,
    w: int,
    h: int,
    bounds: tuple[int, int, int, int],
) -> bool:
    x1, y1, x2, y2 = bounds
    return x >= x1 and y >= y1 and x + w <= x2 and y + h <= y2


def _remove_text_like_components(
    candidate: np.ndarray,
    group_bbox: tuple[int, int, int, int],
) -> np.ndarray:
    """Remove small dark strokes near the text group from frame candidates.

    Ruby/furigana and missed tiny glyphs are often outside the OCR text box, so
    subtracting only the OCR rectangles is not enough. A valid bubble frame near
    the text should have meaningful pixels on opposing sides of the group; small
    one-sided components near the group are treated as text residue instead.
    """
    bx1, by1, bx2, by2 = group_bbox
    gw = max(1, bx2 - bx1)
    gh = max(1, by2 - by1)
    group_area = gw * gh
    pad_x = max(14, int(round(gw * 0.85)))
    pad_y = max(14, int(round(gh * 1.35)))
    text_zone = (
        max(0, bx1 - pad_x),
        max(0, by1 - pad_y),
        min(candidate.shape[1], bx2 + pad_x),
        min(candidate.shape[0], by2 + pad_y),
    )

    filtered = candidate.copy()
    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats((candidate > 0).astype(np.uint8), 8)
    for label in range(1, num_labels):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        cw = int(stats[label, cv2.CC_STAT_WIDTH])
        ch = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area <= 0:
            continue

        component = (labels == label).astype(np.uint8) * 255
        left, right, top, bottom = _component_side_hits(component, group_bbox)
        has_opposing_sides = (left and right) or (top and bottom)
        small_for_frame = area < max(120, int(round(group_area * 0.55)))
        mostly_near_text = _component_bbox_inside(x, y, cw, ch, text_zone)

        if mostly_near_text and small_for_frame and not has_opposing_sides:
            filtered[labels == label] = 0

    return filtered


def _build_frame_candidate(
    crop: np.ndarray,
    required_text: np.ndarray,
    group_bbox: tuple[int, int, int, int],
) -> np.ndarray:
    gray = cv2.cvtColor(crop, cv2.COLOR_RGB2GRAY)
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    v = float(np.median(blur))
    lo = int(max(0, 0.60 * v))
    hi = int(min(255, 1.40 * v + 12))
    edges = cv2.Canny(blur, lo, hi, L2gradient=True)

    candidate = cv2.bitwise_or(edges, _dark_line_mask(crop))
    candidate = cv2.morphologyEx(
        candidate,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
        iterations=1,
    )
    text_guard = cv2.dilate(
        required_text,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)),
        iterations=1,
    )
    candidate[text_guard > 0] = 0
    return _remove_text_like_components(candidate, group_bbox)


def _component_side_hits(component: np.ndarray, group_bbox: tuple[int, int, int, int]) -> tuple[bool, bool, bool, bool]:
    bx1, by1, bx2, by2 = group_bbox
    ys, xs = np.where(component > 0)
    if xs.size == 0:
        return False, False, False, False
    min_hits = max(3, int(round(min(max(1, bx2 - bx1), max(1, by2 - by1)) * 0.05)))
    left = int(np.count_nonzero(xs < bx1)) >= min_hits
    right = int(np.count_nonzero(xs >= bx2)) >= min_hits
    top = int(np.count_nonzero(ys < by1)) >= min_hits
    bottom = int(np.count_nonzero(ys >= by2)) >= min_hits
    return left, right, top, bottom


def _select_frame_boundary(
    crop: np.ndarray,
    frame_candidate: np.ndarray,
    required_text: np.ndarray,
    group_bbox: tuple[int, int, int, int],
    center: tuple[int, int],
) -> tuple[np.ndarray, bool]:
    h, w = crop.shape[:2]
    bx1, by1, bx2, by2 = group_bbox
    gw = max(1, bx2 - bx1)
    gh = max(1, by2 - by1)
    group_area = float(gw * gh)
    crop_area = float(max(1, h * w))

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats((frame_candidate > 0).astype(np.uint8), 8)
    best_label = -1
    best_score = -1.0
    for label in range(1, num_labels):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        cw = int(stats[label, cv2.CC_STAT_WIDTH])
        ch = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        if area < max(12, int(round((gw + gh) * 0.15))):
            continue

        cbx2 = x + cw
        cby2 = y + ch
        bbox_area = float(max(1, cw * ch))
        if bbox_area < group_area * 1.2:
            continue
        if bbox_area > crop_area * 0.92 and (x <= 1 or y <= 1 or cbx2 >= w - 1 or cby2 >= h - 1):
            continue

        center_inside = x - 3 <= center[0] <= cbx2 + 3 and y - 3 <= center[1] <= cby2 + 3
        larger_than_text = x < bx1 or y < by1 or cbx2 > bx2 or cby2 > by2
        if not center_inside or not larger_than_text:
            continue

        component = (labels == label).astype(np.uint8) * 255
        text_overlap = int(np.count_nonzero(cv2.bitwise_and(component, required_text)))
        if text_overlap / max(1, area) > 0.35:
            continue

        left, right, top, bottom = _component_side_hits(component, group_bbox)
        opposing_pairs = int(left and right) + int(top and bottom)
        if opposing_pairs == 0:
            continue

        span_score = (cw / max(1.0, float(gw))) + (ch / max(1.0, float(gh)))
        score = area + 1000.0 * opposing_pairs + 50.0 * span_score
        if score > best_score:
            best_label = label
            best_score = score

    if best_label >= 0:
        boundary = (labels == best_label).astype(np.uint8) * 255
        boundary = cv2.morphologyEx(
            boundary,
            cv2.MORPH_CLOSE,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)),
            iterations=1,
        )
        boundary = cv2.dilate(boundary, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)), iterations=1)
        return boundary, True

    fallback = frame_candidate.copy()
    fallback[0, :] = 255
    fallback[-1, :] = 255
    fallback[:, 0] = 255
    fallback[:, -1] = 255
    return fallback, False


def _interior_from_boundary(boundary: np.ndarray, center: tuple[int, int]) -> np.ndarray | None:
    h, w = boundary.shape[:2]
    blocked = cv2.dilate(
        (boundary > 0).astype(np.uint8) * 255,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)),
        iterations=1,
    )
    free = cv2.bitwise_not(blocked)
    flood = free.copy()
    ff_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)

    for x in range(w):
        if flood[0, x] == 255:
            cv2.floodFill(flood, ff_mask, (x, 0), 127)
        if flood[h - 1, x] == 255:
            cv2.floodFill(flood, ff_mask, (x, h - 1), 127)
    for y in range(h):
        if flood[y, 0] == 255:
            cv2.floodFill(flood, ff_mask, (0, y), 127)
        if flood[y, w - 1] == 255:
            cv2.floodFill(flood, ff_mask, (w - 1, y), 127)

    interior = ((flood == 255).astype(np.uint8)) * 255
    cx = min(max(int(center[0]), 0), w - 1)
    cy = min(max(int(center[1]), 0), h - 1)
    if interior[cy, cx] > 0 and np.count_nonzero(interior) > 0:
        return interior

    num_labels, labels, stats, _ = cv2.connectedComponentsWithStats((free > 0).astype(np.uint8), 8)
    center_label = int(labels[cy, cx])
    if center_label <= 0:
        return None

    x = int(stats[center_label, cv2.CC_STAT_LEFT])
    y = int(stats[center_label, cv2.CC_STAT_TOP])
    cw = int(stats[center_label, cv2.CC_STAT_WIDTH])
    ch = int(stats[center_label, cv2.CC_STAT_HEIGHT])
    touches_edge = x <= 0 or y <= 0 or x + cw >= w or y + ch >= h
    if touches_edge:
        return None
    return (labels == center_label).astype(np.uint8) * 255


def _ellipse_is_blocked(candidate: np.ndarray, boundary: np.ndarray, interior: np.ndarray | None) -> bool:
    ring = cv2.subtract(
        cv2.dilate(candidate, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)), iterations=1),
        candidate,
    )
    if np.count_nonzero(cv2.bitwise_and(ring, boundary)) > 0:
        return True
    if interior is None:
        return False

    outside = cv2.bitwise_and(candidate, cv2.bitwise_not(interior))
    outside_count = int(np.count_nonzero(outside))
    tolerance = max(3, int(round(np.count_nonzero(candidate) * 0.003)))
    return outside_count > tolerance


def _grow_ellipse_to_frame(
    shape: tuple[int, int],
    center: tuple[int, int],
    group_bbox: tuple[int, int, int, int],
    boundary: np.ndarray,
    interior: np.ndarray | None,
    required_text: np.ndarray,
    max_scale: float | None = None,
) -> np.ndarray:
    bx1, by1, bx2, by2 = group_bbox
    required_bbox = _text_mask_bbox(required_text) or group_bbox
    rx1, ry1, rx2, ry2 = required_bbox

    base_x = max(2, int(np.ceil(max(bx2 - bx1, rx2 - rx1) * 0.5)) + 2)
    base_y = max(2, int(np.ceil(max(by2 - by1, ry2 - ry1) * 0.5)) + 2)
    if max_scale is None:
        max_axis_x = max(base_x, shape[1])
        max_axis_y = max(base_y, shape[0])
    else:
        scale = max(1.0, float(max_scale))
        max_axis_x = max(base_x, min(shape[1], int(round(base_x * scale))))
        max_axis_y = max(base_y, min(shape[0], int(round(base_y * scale))))
    step_x = max(1, int(round(base_x * 0.08)))
    step_y = max(1, int(round(base_y * 0.08)))

    ax = base_x
    ay = base_y
    chosen = _ellipse_mask(shape, center, (ax, ay))
    freeze_x = _ellipse_is_blocked(_ellipse_mask(shape, center, (ax + 1, ay)), boundary, interior)
    freeze_y = _ellipse_is_blocked(_ellipse_mask(shape, center, (ax, ay + 1)), boundary, interior)

    for _ in range(768):
        changed = False
        if not freeze_x and ax < max_axis_x:
            next_ax = min(max_axis_x, ax + step_x)
            candidate = _ellipse_mask(shape, center, (next_ax, ay))
            if _ellipse_is_blocked(candidate, boundary, interior):
                freeze_x = True
            else:
                ax = next_ax
                chosen = candidate
                changed = True

        if not freeze_y and ay < max_axis_y:
            next_ay = min(max_axis_y, ay + step_y)
            candidate = _ellipse_mask(shape, center, (ax, next_ay))
            if _ellipse_is_blocked(candidate, boundary, interior):
                freeze_y = True
            else:
                ay = next_ay
                chosen = candidate
                changed = True

        if (freeze_x or ax >= max_axis_x) and (freeze_y or ay >= max_axis_y):
            break
        if not changed and (freeze_x or ax >= max_axis_x) and (freeze_y or ay >= max_axis_y):
            break

    if interior is not None:
        chosen = cv2.bitwise_and(chosen, interior)
    return cv2.bitwise_or(chosen, required_text)


def _extract_elliptic_bubble_mask_local(
    raw_image: np.ndarray,
    rx: int,
    ry: int,
    rw: int,
    rh: int,
    *,
    text_mask_local: np.ndarray,
    enlarge_ratio: float,
    text_boxes: list[tuple[int, int, int, int]] | None = None,
) -> tuple[np.ndarray, list[int]] | tuple[None, None]:
    if rw <= 2 or rh <= 2:
        return None, None

    lx1, ly1, lx2, ly2 = _region_window(raw_image.shape, rx, ry, rw, rh, enlarge_ratio)
    if lx2 <= lx1 or ly2 <= ly1:
        return None, None

    crop = raw_image[ly1:ly2, lx1:lx2]
    if crop.size == 0:
        return None, None

    local_text = np.zeros(crop.shape[:2], dtype=np.uint8)
    tx1 = max(0, rx - lx1)
    ty1 = max(0, ry - ly1)
    tx2 = min(local_text.shape[1], tx1 + text_mask_local.shape[1])
    ty2 = min(local_text.shape[0], ty1 + text_mask_local.shape[0])
    if tx2 > tx1 and ty2 > ty1:
        local_text[ty1:ty2, tx1:tx2] = (text_mask_local[:ty2 - ty1, :tx2 - tx1] > 0).astype(np.uint8) * 255

    group_bbox = (
        max(0, rx - lx1),
        max(0, ry - ly1),
        min(crop.shape[1], rx + rw - lx1),
        min(crop.shape[0], ry + rh - ly1),
    )
    if text_boxes:
        local_boxes = [
            (x - lx1, y - ly1, w, h)
            for x, y, w, h in text_boxes
        ]
        required_text = _required_text_mask_from_boxes(crop.shape[:2], local_boxes)
    else:
        required_text = _required_text_mask(crop.shape[:2], group_bbox)
    required_text = cv2.bitwise_or(required_text, local_text)

    tb = _text_mask_bbox(required_text)
    if tb is None:
        return None, None
    bx1, by1, bx2, by2 = tb
    center = (int(round((bx1 + bx2) * 0.5)), int(round((by1 + by2) * 0.5)))

    frame_candidate = _build_frame_candidate(crop, required_text, group_bbox)
    boundary, confident_boundary = _select_frame_boundary(crop, frame_candidate, required_text, group_bbox, center)
    interior = _interior_from_boundary(boundary, center) if confident_boundary else None

    fallback_scale = None if confident_boundary else min(2.4, max(1.0, float(enlarge_ratio) * 0.4))
    grown = _grow_ellipse_to_frame(crop.shape[:2], center, group_bbox, boundary, interior, required_text, fallback_scale)
    if interior is None:
        # Borderless or broken-frame fallback: keep a local ellipse only. The
        # global area-ratio guard will reject anything too large.
        grown = cv2.bitwise_or(grown, required_text)
    else:
        grown = cv2.bitwise_or(cv2.bitwise_and(grown, interior), required_text)
    return (grown > 0).astype(np.uint8) * 255, [lx1, ly1, lx2, ly2]


def _merge_bubble_mask_prior(
    final_mask: np.ndarray,
    text_regions: List[TextBlock],
    raw_image: np.ndarray,
    *,
    mode: str,
    enabled: bool,
    enlarge_ratio: float,
    min_area_ratio: float,
    max_area_ratio: float,
) -> np.ndarray:
    if not enabled or mode == "off" or final_mask is None or final_mask.size == 0:
        return final_mask

    h, w = final_mask.shape[:2]
    expanded_union = np.zeros((h, w), dtype=np.uint8)

    for group in _group_text_boxes(text_regions):
        rx, ry, rw, rh = group.bbox
        rx1 = max(0, rx)
        ry1 = max(0, ry)
        rx2 = min(raw_image.shape[1], rx + rw)
        ry2 = min(raw_image.shape[0], ry + rh)
        if rx2 <= rx1 or ry2 <= ry1:
            continue

        local_mask, rect = _extract_elliptic_bubble_mask_local(
            raw_image,
            rx,
            ry,
            rw,
            rh,
            text_mask_local=final_mask[ry1:ry2, rx1:rx2],
            enlarge_ratio=max(float(enlarge_ratio), 1.0),
            text_boxes=group.boxes,
        )
        if local_mask is None or rect is None or local_mask.size == 0:
            continue

        lx1, ly1, lx2, ly2 = [int(v) for v in rect]
        lx1 = max(0, min(lx1, w))
        lx2 = max(0, min(lx2, w))
        ly1 = max(0, min(ly1, h))
        ly2 = max(0, min(ly2, h))
        if lx2 <= lx1 or ly2 <= ly1:
            continue

        crop_h = ly2 - ly1
        crop_w = lx2 - lx1
        local_bin = ((local_mask[:crop_h, :crop_w] > 0).astype(np.uint8)) * 255
        if local_bin.size == 0:
            continue

        bubble_area = int(np.count_nonzero(local_bin))
        group_area = max(int(rw * rh), 1)
        area_ratio = bubble_area / group_area
        if area_ratio < float(min_area_ratio) or area_ratio > float(max_area_ratio):
            continue

        if mode == "full":
            grown = local_bin
        else:
            grown = local_bin

        expanded_union[ly1:ly2, lx1:lx2] = np.maximum(
            expanded_union[ly1:ly2, lx1:lx2],
            grown,
        )

    if np.any(expanded_union):
        return cv2.bitwise_or(final_mask, expanded_union)
    return final_mask


async def dispatch(
    text_regions: List[TextBlock],
    raw_image: np.ndarray,
    raw_mask: np.ndarray,
    method: str = 'fit_text',
    dilation_offset: int = 0,
    ignore_bubble: int = 0,
    verbose: bool = False,
    kernel_size: int = 3,
    bubble_mask_mode: str = "expand_text",
    bubble_mask_prior: bool = True,
    bubble_mask_enlarge_ratio: float = 1.6,
    bubble_mask_min_area_ratio: float = 0.35,
    bubble_mask_max_area_ratio: float = 8.0,
) -> np.ndarray:
    # Larger mask images preserve thinner mask segments, so avoid downscaling
    # them too aggressively before fitting text components.
    scale_factor = max(min((raw_mask.shape[0] - raw_image.shape[0] / 3) / raw_mask.shape[0], 1), 0.5)

    img_resized = cv2.resize(raw_image, (int(raw_image.shape[1] * scale_factor), int(raw_image.shape[0] * scale_factor)), interpolation=cv2.INTER_LINEAR)
    mask_resized = cv2.resize(raw_mask, (int(raw_image.shape[1] * scale_factor), int(raw_image.shape[0] * scale_factor)), interpolation=cv2.INTER_LINEAR)

    mask_resized[mask_resized > 0] = 255
    textlines = []
    for region in text_regions:
        for line in region.lines:
            textlines.append(Quadrilateral(line * scale_factor, '', 0))

    final_mask = complete_mask(img_resized, mask_resized, textlines, dilation_offset=dilation_offset, kernel_size=kernel_size) if method == 'fit_text' else complete_mask_fill([txtln.aabb.xywh for txtln in textlines])
    if final_mask is None:
        final_mask = np.zeros((raw_image.shape[0], raw_image.shape[1]), dtype=np.uint8)
    else:
        final_mask = cv2.resize(final_mask, (raw_image.shape[1], raw_image.shape[0]), interpolation=cv2.INTER_LINEAR)
        final_mask[final_mask > 0] = 255

    final_mask = _merge_bubble_mask_prior(
        final_mask,
        text_regions,
        raw_image,
        mode=(bubble_mask_mode or "full"),
        enabled=bubble_mask_prior,
        enlarge_ratio=bubble_mask_enlarge_ratio,
        min_area_ratio=bubble_mask_min_area_ratio,
        max_area_ratio=bubble_mask_max_area_ratio,
    )

    if ignore_bubble < 1 or ignore_bubble > 50:
        return final_mask

    kernel_size = int(max(final_mask.shape) * 0.025)
    kernel_size = max(3, kernel_size | 1)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
    final_mask = cv2.dilate(final_mask, kernel, iterations=1)
    contours, _ = cv2.findContours(final_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        temp_mask = np.zeros_like(final_mask)
        x, y, box_w, box_h = cv2.boundingRect(cnt)
        cv2.rectangle(temp_mask, (x, y), (x + box_w, y + box_h), 255, -1)
        textblock = cv2.bitwise_and(raw_image, raw_image, mask=temp_mask)
        if is_ignore(textblock, ignore_bubble):
            cv2.drawContours(final_mask, [cnt], -1, 0, -1)

    return final_mask
