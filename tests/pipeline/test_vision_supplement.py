"""Tests for vision-supplemented bubble detection (Experiment #14)."""
from mga.models import BoundingBox, Bubble, Page, PageImage, ProjectConfig
from mga.pipeline.stages import PipelineContext
from mga.pipeline.vision_stage import (
    VisionEnrichmentStage,
    _build_cover_title_focus_prompt,
    _build_vision_prompt,
    _compute_iou,
)
from PIL import Image, ImageDraw


class TestVisionPrompt:
    def test_cover_title_prompt_requests_tight_split_boxes(self):
        prompt = _build_vision_prompt()

        assert "cover_title" in prompt
        assert "Split the title" in prompt
        assert "bbox tightly covers only the visible strokes" in prompt
        assert "relative to the image you receive" in prompt
        assert "SINGLE bounding box" not in prompt

    def test_cover_title_focus_prompt_describes_high_contrast_preprocessing(self):
        prompt = _build_cover_title_focus_prompt()

        assert "high-contrast black-on-white OCR" in prompt
        assert "second image is the original crop" in prompt


class TestCoverTitlePreprocessing:
    def test_white_title_crop_is_converted_to_black_on_white_ocr_image(self):
        import io
        import numpy as np

        img = Image.new("RGB", (120, 240), (180, 95, 55))
        draw = ImageDraw.Draw(img)
        draw.rectangle((40, 20, 80, 210), fill=(252, 250, 245))

        processed = VisionEnrichmentStage._preprocess_cover_title_crop_for_ocr(img)

        assert processed is not None
        out = Image.open(io.BytesIO(processed)).convert("L")
        arr = np.asarray(out)
        assert float((arr < 64).mean()) > 0.05
        assert float((arr > 240).mean()) > 0.5


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

    def test_cover_title_is_added_instead_of_matching_ocr_order(self):
        ocr_bubbles = [
            Bubble(
                bubble_id="region-0000-0000",
                bbox=BoundingBox(x=50, y=500, width=140, height=40),
                source_text="COMICS",
                reading_order=0,
                detection_source="ocr",
            ),
        ]
        page = self._make_page(ocr_bubbles)
        page.page_index = 0

        vision_result = {
            "bubbles": [
                {
                    "source_text": "私を喰べたい",
                    "bbox": {"x": 100, "y": 80, "width": 240, "height": 420},
                    "box_type": "cover_title",
                    "reading_order": 0,
                    "confidence": 0.95,
                },
            ],
            "visual_footnotes": [],
            "voice_hints": [],
            "scene_summary": "",
        }

        stage = VisionEnrichmentStage()
        stage._apply_enrichment_to_page(page, vision_result)

        assert [bubble.bubble_id for bubble in page.bubbles] == [
            "region-0000-0000",
            "vision-0000-0000",
        ]
        assert page.bubbles[0].source_text == "COMICS"
        assert page.bubbles[1].source_text == "私を喰べたい"
        assert page.bubbles[1].box_type == "cover_title"

    def test_cover_title_single_character_fragments_are_merged(self):
        page = self._make_page([])
        page.page_index = 0
        vision_result = {
            "bubbles": [
                {"source_text": "8", "bbox": {"x": 130, "y": 25, "width": 50, "height": 50}, "box_type": "cover_title", "reading_order": 0},
                {"source_text": "私", "bbox": {"x": 470, "y": 20, "width": 90, "height": 130}, "box_type": "cover_title", "reading_order": 1},
                {"source_text": "を", "bbox": {"x": 510, "y": 150, "width": 70, "height": 100}, "box_type": "cover_title", "reading_order": 2},
                {"source_text": "喰", "bbox": {"x": 470, "y": 260, "width": 110, "height": 130}, "box_type": "cover_title", "reading_order": 3},
                {"source_text": "べ", "bbox": {"x": 510, "y": 395, "width": 70, "height": 100}, "box_type": "cover_title", "reading_order": 4},
                {"source_text": "た", "bbox": {"x": 470, "y": 510, "width": 90, "height": 110}, "box_type": "cover_title", "reading_order": 5},
                {"source_text": "い", "bbox": {"x": 510, "y": 625, "width": 60, "height": 100}, "box_type": "cover_title", "reading_order": 6},
                {"source_text": "ひ", "bbox": {"x": 30, "y": 25, "width": 80, "height": 110}, "box_type": "cover_title", "reading_order": 7},
                {"source_text": "と", "bbox": {"x": 30, "y": 145, "width": 80, "height": 110}, "box_type": "cover_title", "reading_order": 8},
                {"source_text": "で", "bbox": {"x": 30, "y": 265, "width": 80, "height": 110}, "box_type": "cover_title", "reading_order": 9},
                {"source_text": "な", "bbox": {"x": 30, "y": 385, "width": 80, "height": 110}, "box_type": "cover_title", "reading_order": 10},
                {"source_text": "し", "bbox": {"x": 30, "y": 505, "width": 80, "height": 110}, "box_type": "cover_title", "reading_order": 11},
                {"source_text": "苗川采", "bbox": {"x": 365, "y": 380, "width": 50, "height": 130}, "box_type": "cover_title", "reading_order": 12},
                {"source_text": "NEXT", "bbox": {"x": 100, "y": 760, "width": 100, "height": 25}, "box_type": "cover_title", "reading_order": 13},
            ],
            "visual_footnotes": [],
            "voice_hints": [],
            "scene_summary": "",
        }

        stage = VisionEnrichmentStage()
        stage._apply_enrichment_to_page(page, vision_result)

        cover_texts = [b.source_text for b in page.bubbles if b.box_type == "cover_title"]
        assert "私を喰べたい" in cover_texts
        assert "ひとでなし" in cover_texts
        assert "8" in cover_texts
        assert "苗川采" in cover_texts
        assert "NEXT" in cover_texts
        assert "喰" not in cover_texts
        assert "し" not in cover_texts

    def test_cover_title_short_column_fragments_are_merged(self):
        page = self._make_page([])
        page.page_index = 0
        vision_result = {
            "bubbles": [
                {"source_text": "私を", "bbox": {"x": 1200, "y": 52, "width": 340, "height": 338}, "box_type": "cover_title", "reading_order": 0},
                {"source_text": "喰べ", "bbox": {"x": 1200, "y": 430, "width": 340, "height": 338}, "box_type": "cover_title", "reading_order": 1},
                {"source_text": "たい、", "bbox": {"x": 1200, "y": 807, "width": 340, "height": 338}, "box_type": "cover_title", "reading_order": 2},
                {"source_text": "ひとで", "bbox": {"x": 0, "y": 65, "width": 340, "height": 338}, "box_type": "cover_title", "reading_order": 3},
                {"source_text": "なし", "bbox": {"x": 0, "y": 430, "width": 340, "height": 338}, "box_type": "cover_title", "reading_order": 4},
                {"source_text": "苗川采", "bbox": {"x": 938, "y": 886, "width": 156, "height": 468}, "box_type": "cover_title", "reading_order": 5},
                {"source_text": "NAEKAWA SAI", "bbox": {"x": 1108, "y": 990, "width": 78, "height": 338}, "box_type": "cover_title", "reading_order": 6},
            ],
            "visual_footnotes": [],
            "voice_hints": [],
            "scene_summary": "",
        }

        stage = VisionEnrichmentStage()
        stage._apply_enrichment_to_page(page, vision_result)

        cover_texts = [b.source_text for b in page.bubbles if b.box_type == "cover_title"]
        assert "私を喰べたい、" in cover_texts
        assert "ひとでなし" in cover_texts
        assert "苗川采" in cover_texts
        assert "NAEKAWA SAI" in cover_texts
        assert "ひとで" not in cover_texts
        assert "なし" not in cover_texts

    def test_missing_cover_title_column_gets_focused_supplement(self, tmp_path):
        image_path = tmp_path / "cover.png"
        img = Image.new("RGB", (1000, 1400), (190, 110, 70))
        draw = ImageDraw.Draw(img)
        draw.rectangle((40, 80, 180, 1180), fill=(250, 250, 248))
        draw.rectangle((820, 80, 960, 1180), fill=(250, 250, 248))
        img.save(image_path)

        page = self._make_page([
            Bubble(
                bubble_id="vision-0000-0000",
                bbox=BoundingBox(x=820, y=80, width=140, height=1100),
                source_text="私を喰べたい",
                reading_order=0,
                detection_source="vision",
                box_type="cover_title",
            )
        ])
        page.page_index = 0
        page.image = PageImage(path=str(image_path), width=1000, height=1400)

        class FocusProvider:
            errors = []
            calls = []

            def call_vision_structured(self, **kwargs):
                self.calls.append(kwargs.get("operation"))
                return (
                    {
                        "bubbles": [
                            {
                                "source_text": "ひとでなし",
                                "bbox": {"x": 10, "y": 20, "width": 100, "height": 800},
                                "box_type": "cover_title",
                                "confidence": 0.9,
                            }
                        ]
                    },
                    object(),
                )

        stage = VisionEnrichmentStage()
        stage._supplement_missing_cover_title_columns(page, FocusProvider(), ProjectConfig())

        cover_texts = [b.source_text for b in page.bubbles if b.box_type == "cover_title"]
        assert "私を喰べたい" in cover_texts
        assert "ひとでなし" in cover_texts
        assert page.bubbles[-1].bbox.x >= 40

    def test_missing_cover_title_column_supplements_when_existing_count_matches_columns(self, tmp_path):
        image_path = tmp_path / "cover.png"
        img = Image.new("RGB", (1000, 1400), (190, 110, 70))
        draw = ImageDraw.Draw(img)
        draw.rectangle((40, 80, 180, 1180), fill=(250, 250, 248))
        draw.rectangle((820, 80, 960, 1180), fill=(250, 250, 248))
        img.save(image_path)

        page = self._make_page([
            Bubble(
                bubble_id="vision-0000-0000",
                bbox=BoundingBox(x=820, y=80, width=140, height=360),
                source_text="私を",
                reading_order=0,
                detection_source="vision",
                box_type="cover_title",
            ),
            Bubble(
                bubble_id="vision-0000-0001",
                bbox=BoundingBox(x=820, y=460, width=140, height=360),
                source_text="喰べ",
                reading_order=1,
                detection_source="vision",
                box_type="cover_title",
            ),
        ])
        page.page_index = 0
        page.image = PageImage(path=str(image_path), width=1000, height=1400)

        class FocusProvider:
            errors = []
            calls = []

            def call_vision_structured(self, **kwargs):
                self.calls.append(kwargs.get("operation"))
                return (
                    {
                        "bubbles": [
                            {
                                "source_text": "ひとでなし",
                                "bbox": {"x": 10, "y": 20, "width": 100, "height": 800},
                                "box_type": "cover_title",
                                "confidence": 0.9,
                            }
                        ]
                    },
                    object(),
                )

        provider = FocusProvider()
        stage = VisionEnrichmentStage()
        stage._supplement_missing_cover_title_columns(page, provider, ProjectConfig())

        cover_texts = [b.source_text for b in page.bubbles if b.box_type == "cover_title"]
        assert "ひとでなし" in cover_texts
        assert provider.calls == ["vision_cover_title_focus"]


    def test_cover_title_focus_sends_processed_crop_before_raw_crop(self, tmp_path):
        image_path = tmp_path / "cover.png"
        img = Image.new("RGB", (1000, 1400), (190, 110, 70))
        draw = ImageDraw.Draw(img)
        draw.rectangle((40, 80, 180, 1180), fill=(250, 250, 248))
        draw.rectangle((820, 80, 960, 1180), fill=(250, 250, 248))
        img.save(image_path)

        page = self._make_page([
            Bubble(
                bubble_id="vision-0000-0000",
                bbox=BoundingBox(x=820, y=80, width=140, height=1100),
                source_text="あああ",
                reading_order=0,
                detection_source="vision",
                box_type="cover_title",
            )
        ])
        page.page_index = 0
        page.image = PageImage(path=str(image_path), width=1000, height=1400)

        class FocusProvider:
            errors = []
            calls = []
            image_counts = []

            def call_vision_structured(self, **kwargs):
                self.calls.append(kwargs.get("operation"))
                self.image_counts.append(len(kwargs.get("images") or []))
                return (
                    {
                        "bubbles": [
                            {
                                "source_text": "いいい",
                                "bbox": {"x": 10, "y": 20, "width": 100, "height": 800},
                                "box_type": "cover_title",
                                "confidence": 0.9,
                            }
                        ]
                    },
                    object(),
                )

        provider = FocusProvider()
        stage = VisionEnrichmentStage()
        stage._supplement_missing_cover_title_columns(page, provider, ProjectConfig())

        assert provider.calls == ["vision_cover_title_focus"]
        assert provider.image_counts == [2]

    def test_cover_title_corrections_replace_overlapping_vision_titles(self, tmp_path):
        image_path = tmp_path / "cover.png"
        img = Image.new("RGB", (1000, 1400), (190, 110, 70))
        draw = ImageDraw.Draw(img)
        draw.rectangle((40, 80, 180, 1180), fill=(250, 250, 248))
        draw.rectangle((820, 80, 960, 1180), fill=(250, 250, 248))
        img.save(image_path)

        page = self._make_page([
            Bubble(
                bubble_id="vision-0000-wrong-right",
                bbox=BoundingBox(x=820, y=80, width=140, height=1100),
                source_text="wrong right",
                reading_order=0,
                detection_source="vision",
                box_type="cover_title",
            ),
            Bubble(
                bubble_id="vision-0000-wrong-left",
                bbox=BoundingBox(x=40, y=80, width=140, height=1100),
                source_text="wrong left",
                reading_order=1,
                detection_source="vision",
                box_type="cover_title",
            ),
        ])
        page.page_index = 0
        page.image = PageImage(path=str(image_path), width=1000, height=1400)
        cfg = ProjectConfig(
            plugins={
                "cover_title_corrections": {
                    "pages": {
                        "page_0000": {
                            "source_texts": ["私を喰べたい", "ひとでなし"],
                        }
                    }
                }
            }
        )

        VisionEnrichmentStage()._apply_cover_title_corrections(page, cfg)

        cover_titles = [b.source_text for b in page.bubbles if b.box_type == "cover_title"]
        assert cover_titles == ["私を喰べたい", "ひとでなし"]
        assert all("corrected" in b.bubble_id for b in page.bubbles)


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
