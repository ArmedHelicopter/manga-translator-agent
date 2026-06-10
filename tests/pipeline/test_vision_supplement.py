"""Tests for vision-supplemented bubble detection (Experiment #14)."""
from mga.models import BoundingBox, Bubble, Page, PageImage, ProjectConfig
from mga.pipeline.stages import PipelineContext
from mga.pipeline.vision_stage import VisionEnrichmentStage, _compute_iou


class TestComputeIoU:
    def test_no_overlap(self):
        a = BoundingBox(x=0, y=0, width=10, height=10)
        b = BoundingBox(x=20, y=20, width=10, height=10)
        assert _compute_iou(a, b) == 0.0

    def test_full_overlap(self):
        a = BoundingBox(x=0, y=0, width=10, height=10)
        assert _compute_iou(a, a) == 1.0

    def test_partial_overlap(self):
        a = BoundingBox(x=0, y=0, width=10, height=10)
        b = BoundingBox(x=5, y=5, width=10, height=10)
        assert abs(_compute_iou(a, b) - 25 / 175) < 0.01

    def test_zero_area(self):
        a = BoundingBox(x=0, y=0, width=0, height=10)
        b = BoundingBox(x=0, y=0, width=10, height=10)
        assert _compute_iou(a, b) == 0.0


class TestVisionSupplementedBubbles:
    """Test that vision-detected bubbles are added when no OCR match."""

    def _make_page(self, bubbles):
        """Create a mock page with given bubbles."""
        class MockPage:
            def __init__(self):
                self.bubbles = list(bubbles)
                self.page_id = "page_0004"
                self.page_index = 4
                self.scene_summary = ""
                self.visual_footnotes = []

        return MockPage()

    def test_adds_unmatched_vision_bubbles(self):
        """Vision bubbles with no OCR match get added."""
        ocr_bubbles = [
            Bubble(
                bubble_id="region-0004-0000",
                bbox=BoundingBox(x=100, y=100, width=200, height=50),
                source_text="こんにちは",
                reading_order=0,
                detection_source="ocr",
            ),
        ]
        page = self._make_page(ocr_bubbles)

        vision_result = {
            "bubbles": [
                {"bubble_id": "region-0004-0000", "source_text": "こんにちは", "box_type": "dialogue"},
                {
                    "source_text": "さようなら",
                    "bbox": {"x": 500, "y": 500, "width": 180, "height": 40},
                    "box_type": "dialogue",
                    "confidence": 0.85,
                },
                {
                    "source_text": "ドカーン",
                    "bbox": {"x": 800, "y": 200, "width": 100, "height": 100},
                    "box_type": "sfx",
                    "confidence": 0.7,
                },
            ],
            "visual_footnotes": [],
            "voice_hints": [],
            "scene_summary": "Test scene",
        }

        stage = VisionEnrichmentStage()
        stage._apply_enrichment_to_page(page, vision_result)

        assert len(page.bubbles) == 3
        assert page.bubbles[0].detection_source == "ocr"
        assert page.bubbles[1].detection_source == "vision"
        assert page.bubbles[1].source_text == "さようなら"
        assert page.bubbles[1].vision_confidence == 0.85
        assert page.bubbles[2].detection_source == "vision"
        assert page.bubbles[2].source_text == "ドカーン"
        assert page.bubbles[2].box_type == "sfx"

    def test_high_iou_does_not_duplicate(self):
        """Vision bubble overlapping OCR bubble is not added as duplicate."""
        ocr_bubbles = [
            Bubble(
                bubble_id="region-0004-0000",
                bbox=BoundingBox(x=100, y=100, width=200, height=50),
                source_text="こんにちは",
                reading_order=0,
                detection_source="ocr",
            ),
        ]
        page = self._make_page(ocr_bubbles)

        vision_result = {
            "bubbles": [
                {
                    "source_text": "こんにちは",
                    "bbox": {"x": 105, "y": 105, "width": 190, "height": 45},
                    "box_type": "dialogue",
                    "confidence": 0.9,
                    "reading_order": 5,
                },
            ],
            "visual_footnotes": [],
            "voice_hints": [],
            "scene_summary": "",
        }

        stage = VisionEnrichmentStage()
        stage._apply_enrichment_to_page(page, vision_result)

        assert len(page.bubbles) == 1
        assert page.bubbles[0].detection_source == "ocr"

    def test_empty_source_text_not_added(self):
        """Vision bubbles without source_text are skipped."""
        page = self._make_page([])
        vision_result = {
            "bubbles": [
                {"source_text": "", "bbox": {"x": 100, "y": 100, "width": 50, "height": 50}},
                {"bbox": {"x": 200, "y": 200, "width": 50, "height": 50}},
            ],
            "visual_footnotes": [],
            "voice_hints": [],
            "scene_summary": "",
        }

        stage = VisionEnrichmentStage()
        stage._apply_enrichment_to_page(page, vision_result)

        assert len(page.bubbles) == 0

    def test_ocr_text_preserved_when_vision_enriches(self):
        """OCR source_text is never overwritten by vision."""
        ocr_bubbles = [
            Bubble(
                bubble_id="region-0004-0000",
                bbox=BoundingBox(x=100, y=100, width=200, height=50),
                source_text="OCR_AUTHORITATIVE_TEXT",
                reading_order=0,
                detection_source="ocr",
            ),
        ]
        page = self._make_page(ocr_bubbles)

        vision_result = {
            "bubbles": [
                {
                    "bubble_id": "region-0004-0000",
                    "source_text": "VISION_DIFFERENT_TEXT",
                    "box_type": "dialogue",
                },
            ],
            "visual_footnotes": [],
            "voice_hints": [],
            "scene_summary": "",
        }

        stage = VisionEnrichmentStage()
        stage._apply_enrichment_to_page(page, vision_result)

        assert page.bubbles[0].source_text == "OCR_AUTHORITATIVE_TEXT"


class TestZeroVisionCallsWarning:
    """Zero successful vision calls across all pages must produce a loud warning."""

    def _ctx_with_ocr_page(self, tmp_path):
        page = Page(
            page_id="page_0000",
            page_index=0,
            image=PageImage(path=str(tmp_path / "missing.png")),
            bubbles=[
                Bubble(
                    bubble_id="region-0000-0000",
                    bbox=BoundingBox(x=0, y=0, width=10, height=10),
                    source_text="text",
                    reading_order=0,
                )
            ],
        )
        return PipelineContext(project_config=ProjectConfig(), pages=[page])

    def test_warns_when_all_vision_calls_fail(self, tmp_path, monkeypatch, capsys):
        class RejectingProvider:
            def vision_structured(self, messages, images, schema):
                raise RuntimeError("No endpoints found that support image input")

            def vision(self, messages, images):
                raise RuntimeError("No endpoints found that support image input")

        image_path = tmp_path / "page.png"
        image_path.write_bytes(b"img")
        ctx = self._ctx_with_ocr_page(tmp_path)
        ctx.pages[0].image.path = str(image_path)
        monkeypatch.setattr(
            "mga.providers.cascade.get_provider",
            lambda name, **settings: RejectingProvider(),
        )

        ctx = VisionEnrichmentStage().execute(ctx)

        artifact = ctx.artifacts["vision"]
        assert "warning" in artifact
        assert "0 successful provider calls" in artifact["warning"]
        out = capsys.readouterr().out
        assert "WARNING" in out

    def test_no_warning_when_calls_succeed(self, tmp_path, monkeypatch, capsys):
        class OkProvider:
            def vision_structured(self, messages, images, schema):
                return {"bubbles": [], "visual_footnotes": [], "voice_hints": [], "scene_summary": ""}

        image_path = tmp_path / "page.png"
        image_path.write_bytes(b"img")
        ctx = self._ctx_with_ocr_page(tmp_path)
        ctx.pages[0].image.path = str(image_path)
        monkeypatch.setattr(
            "mga.providers.cascade.get_provider",
            lambda name, **settings: OkProvider(),
        )

        ctx = VisionEnrichmentStage().execute(ctx)

        artifact = ctx.artifacts["vision"]
        assert "warning" not in artifact
        assert "WARNING" not in capsys.readouterr().out
