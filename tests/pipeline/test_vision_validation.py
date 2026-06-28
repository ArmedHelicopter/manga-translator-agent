"""Tests for adversarial validation of vision-LLM bubbles.

Validates that hallucinated / degenerate bubbles (empty text, zero/tiny bbox,
off-page geometry) are dropped before entering the pipeline, and that the
shared validator is used consistently by both the LLM-only and enrichment paths.
"""
from __future__ import annotations

from mga.models import Bubble, Page, PageImage
from mga.pipeline.vision_stage import VisionEnrichmentStage


class TestValidateVisionBubble:
    def test_accepts_valid_in_bounds_bbox(self):
        raw = {"source_text": "こんにちは", "bbox": {"x": 100, "y": 100, "width": 50, "height": 30}}
        result = VisionEnrichmentStage._validate_vision_bubble(raw, 1000, 1000)
        assert result is not None
        bbox, src = result
        assert src == "こんにちは"
        assert (bbox.x, bbox.y, bbox.width, bbox.height) == (100.0, 100.0, 50.0, 30.0)

    def test_accepts_lines_format(self):
        raw = {"source_text": "世界", "lines": [[[100, 100], [150, 100], [150, 130], [100, 130]]]}
        result = VisionEnrichmentStage._validate_vision_bubble(raw, 1000, 1000)
        assert result is not None
        bbox, _ = result
        assert bbox.width == 50.0 and bbox.height == 30.0

    def test_rejects_empty_source_text(self):
        raw = {"source_text": "   ", "bbox": {"x": 100, "y": 100, "width": 50, "height": 30}}
        assert VisionEnrichmentStage._validate_vision_bubble(raw, 1000, 1000) is None

    def test_rejects_missing_source_text(self):
        raw = {"bbox": {"x": 100, "y": 100, "width": 50, "height": 30}}
        assert VisionEnrichmentStage._validate_vision_bubble(raw, 1000, 1000) is None

    def test_rejects_zero_width_bbox(self):
        raw = {"source_text": "x", "bbox": {"x": 100, "y": 100, "width": 0, "height": 30}}
        assert VisionEnrichmentStage._validate_vision_bubble(raw, 1000, 1000) is None

    def test_rejects_tiny_area_bbox(self):
        raw = {"source_text": "x", "bbox": {"x": 100, "y": 100, "width": 4, "height": 4}}
        # area 16 < 64 threshold
        assert VisionEnrichmentStage._validate_vision_bubble(raw, 1000, 1000) is None

    def test_rejects_far_off_page_bbox(self):
        raw = {"source_text": "x", "bbox": {"x": 2000, "y": 2000, "width": 50, "height": 30}}
        assert VisionEnrichmentStage._validate_vision_bubble(raw, 1000, 1000) is None

    def test_clamps_minor_overflow(self):
        # box extends 30px past the right edge; bulk is inside → clamp accepted
        raw = {"source_text": "x", "bbox": {"x": 980, "y": 100, "width": 50, "height": 100}}
        result = VisionEnrichmentStage._validate_vision_bubble(raw, 1000, 1000)
        assert result is not None
        bbox, _ = result
        # clamped to the page width
        assert bbox.x + bbox.width <= 1000.0

    def test_skips_bounds_check_when_page_dims_unknown(self):
        # When image dimensions are 0 (e.g. host Page without loaded image),
        # the bounds check is skipped — only text/area validated.
        raw = {"source_text": "x", "bbox": {"x": 99999, "y": 99999, "width": 50, "height": 30}}
        result = VisionEnrichmentStage._validate_vision_bubble(raw, 0, 0)
        assert result is not None


class TestApplyToPageValidates:
    """_apply_to_page must drop hallucinated bubbles via the shared validator."""

    def test_drops_invalid_bubbles_keeps_valid(self):
        stage = VisionEnrichmentStage.__new__(VisionEnrichmentStage)
        page = Page(page_id="page_0000", page_index=0, image=PageImage(width=1000, height=1000))
        result = {
            "bubbles": [
                {"bubble_id": "0", "source_text": "valid", "bbox": {"x": 10, "y": 10, "width": 80, "height": 40}},
                {"bubble_id": "1", "source_text": "", "bbox": {"x": 10, "y": 10, "width": 80, "height": 40}},
                {"bubble_id": "2", "source_text": "tiny", "bbox": {"x": 10, "y": 10, "width": 2, "height": 2}},
            ],
            "scene_summary": "test",
        }
        stage._apply_to_page(page, result)
        assert len(page.bubbles) == 1
        assert page.bubbles[0].source_text == "valid"
        assert page.bubbles[0].detection_source == "vision"
