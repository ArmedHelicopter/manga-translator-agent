"""Tests for the OCR hallucination guard in RenderStage.

Covers:
  - ``_is_blank_region``: blank/white vs. text-bearing vs. unreadable image
  - ``_bbox_from_lines``: OCR ``lines`` polygon → bbox
  - ``_load_region_metadata``: artifact prob/bbox extraction
  - ``_page_input_image_path``: input image resolution from context
  - ``_write_page_translations``: blank regions and low-prob regions are skipped
  - ``__init__`` default threshold
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image

from mga.models import Bubble, BoundingBox, Page, PageImage, ProjectConfig, TranslationCandidate
from mga.models.translation import FootnoteEntry
from mga.pipeline.render_stage import RenderStage
from mga.pipeline.stages import PipelineContext


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_artifact(
    payload_path: Path,
    page_idx: int,
    text_regions: list[dict],
    image_shape: list[int] | None = None,
) -> Path:
    """Write a minimal artifact-NNNN.json with the given text_regions."""
    suffix = f"-{page_idx:04d}"
    artifact = {
        "version": 1,
        "page_index": page_idx,
        "text_regions": text_regions,
        "render_config": {},
        "image_shape": image_shape or [500, 500, 3],
    }
    path = payload_path / f"artifact{suffix}.json"
    path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _make_white_png(path: Path, width: int = 500, height: int = 500) -> Path:
    """Write a pure-white PNG (every pixel 255)."""
    Image.new("RGB", (width, height), (255, 255, 255)).save(path)
    return path


def _make_text_png(path: Path, width: int = 500, height: int = 500) -> Path:
    """Write a PNG with dark text-like pixels in a band so it is NOT blank."""
    img = Image.new("RGB", (width, height), (255, 255, 255))
    px = img.load()
    # Scatter dark pixels across a horizontal band to simulate text.
    for y in range(100, 400):
        for x in range(50, 450, 3):
            px[x, y] = (0, 0, 0)
    img.save(path)
    return path


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------

class TestRenderStageInit:
    def test_default_threshold(self) -> None:
        stage = RenderStage()
        assert stage.ocr_min_prob == 0.25

    def test_custom_threshold(self) -> None:
        stage = RenderStage(ocr_min_prob=0.5)
        assert stage.ocr_min_prob == 0.5

    def test_disable_threshold(self) -> None:
        stage = RenderStage(ocr_min_prob=0.0)
        assert stage.ocr_min_prob == 0.0


# ---------------------------------------------------------------------------
# _bbox_from_lines
# ---------------------------------------------------------------------------

class TestBboxFromLines:
    def test_single_polygon(self) -> None:
        lines = [[[10, 20], [110, 20], [110, 70], [10, 70]]]
        assert RenderStage._bbox_from_lines(lines) == (10, 20, 100, 50)

    def test_multiple_polygons_union(self) -> None:
        # Two disjoint line boxes; bbox is the union bounding box.
        lines = [
            [[2958, 380], [3099, 380], [3099, 760], [2958, 760]],
            [[2781, 385], [2917, 385], [2917, 1291], [2781, 1291]],
            [[2604, 390], [2739, 390], [2739, 1338], [2604, 1338]],
        ]
        # x: 2604..3099, y: 380..1338
        assert RenderStage._bbox_from_lines(lines) == (2604, 380, 495, 958)

    def test_empty_returns_none(self) -> None:
        assert RenderStage._bbox_from_lines([]) is None
        assert RenderStage._bbox_from_lines(None) is None

    def test_zero_area_returns_none(self) -> None:
        # All points identical → zero width/height.
        lines = [[[50, 50], [50, 50]]]
        assert RenderStage._bbox_from_lines(lines) is None

    def test_malformed_returns_none(self) -> None:
        assert RenderStage._bbox_from_lines([[["not", "numbers"]]]) is None


# ---------------------------------------------------------------------------
# _is_blank_region
# ---------------------------------------------------------------------------

class TestIsBlankRegion:
    def test_white_region_is_blank(self, tmp_path: Path) -> None:
        img = _make_white_png(tmp_path / "white.png", width=500, height=500)
        # Region covering the whole image.
        assert RenderStage._is_blank_region(str(img), (0, 0, 500, 500)) is True

    def test_white_subregion_is_blank(self, tmp_path: Path) -> None:
        img = _make_white_png(tmp_path / "white.png", width=500, height=500)
        # A sub-region of a fully white image is also blank.
        assert RenderStage._is_blank_region(str(img), (100, 100, 200, 200)) is True

    def test_text_region_not_blank(self, tmp_path: Path) -> None:
        img = _make_text_png(tmp_path / "text.png", width=500, height=500)
        # The text band (y 100..400) is not blank.
        assert RenderStage._is_blank_region(str(img), (0, 100, 500, 300)) is False

    def test_flat_dark_region_not_blank(self, tmp_path: Path) -> None:
        """A uniform dark block (std=0, mean low) is real content, not a blank
        hallucination. The variance check is gated on mean brightness so it does
        not flag solid-black artwork/fills."""
        import numpy as np
        arr = np.full((200, 200, 3), 10, dtype=np.uint8)  # uniform black
        img = tmp_path / "dark.png"
        Image.fromarray(arr).save(img)
        assert RenderStage._is_blank_region(str(img), (0, 0, 200, 200)) is False

    def test_flat_midgray_region_not_blank(self, tmp_path: Path) -> None:
        """A uniform mid-gray region (std=0, mean=128) is not blank."""
        import numpy as np
        arr = np.full((200, 200, 3), 128, dtype=np.uint8)
        img = tmp_path / "gray.png"
        Image.fromarray(arr).save(img)
        assert RenderStage._is_blank_region(str(img), (0, 0, 200, 200)) is False

    def test_flat_bright_region_is_blank(self, tmp_path: Path) -> None:
        """A uniform bright region (std=0, mean=245) is blank — the variance
        path catches flat bright backgrounds."""
        import numpy as np
        arr = np.full((200, 200, 3), 245, dtype=np.uint8)
        img = tmp_path / "bright.png"
        Image.fromarray(arr).save(img)
        assert RenderStage._is_blank_region(str(img), (0, 0, 200, 200)) is True

    def test_sparse_real_text_is_not_blank(self, tmp_path: Path) -> None:
        """Sparse real text (~3% ink, like short dialogue in an oversized OCR bbox)
        is NOT blank. The ink floor keeps any region with >= 0.5% dark pixels,
        avoiding false positives that a pure near-white heuristic would drop.
        Reproduces the page-009 'あーごめんごめん' edge case."""
        import numpy as np
        # White 200x200 image with ~3% dark pixels (a small text block).
        arr = np.full((200, 200, 3), 255, dtype=np.uint8)
        arr[80:120, 80:100] = (10, 10, 10)  # 40x20 = 800 px of 40000 = 2.0% ink
        img = tmp_path / "sparse_text.png"
        Image.fromarray(arr).save(img)
        assert RenderStage._is_blank_region(str(img), (0, 0, 200, 200)) is False

    def test_just_under_ink_floor_is_blank(self, tmp_path: Path) -> None:
        """A region with < 0.5% ink (a handful of stray pixels) on white is still
        treated as blank — the ink floor only protects regions with real text."""
        import numpy as np
        arr = np.full((200, 200, 3), 255, dtype=np.uint8)  # 40000 px
        # 100 dark pixels = 0.25% ink (< 0.5% floor) → still blank.
        arr[0:10, 0:10] = (10, 10, 10)
        img = tmp_path / "near_blank.png"
        Image.fromarray(arr).save(img)
        assert RenderStage._is_blank_region(str(img), (0, 0, 200, 200)) is True

    def test_unreadable_image_fails_open(self, tmp_path: Path) -> None:
        missing = tmp_path / "does_not_exist.png"
        # Missing file → False (don't skip on unreadable input).
        assert RenderStage._is_blank_region(str(missing), (0, 0, 100, 100)) is False

    def test_zero_size_bbox_not_blank(self, tmp_path: Path) -> None:
        img = _make_white_png(tmp_path / "white.png")
        assert RenderStage._is_blank_region(str(img), (10, 10, 0, 50)) is False
        assert RenderStage._is_blank_region(str(img), (10, 10, 50, 0)) is False

    def test_bbox_clamped_to_image_bounds(self, tmp_path: Path) -> None:
        """A bbox extending past the image edge is clamped; a white image stays blank."""
        img = _make_white_png(tmp_path / "white.png", width=100, height=100)
        # bbox (90, 90, 200, 200) extends past the 100x100 image; clamped to (90,90,10,10).
        assert RenderStage._is_blank_region(str(img), (90, 90, 200, 200)) is True

    def test_bbox_outside_image_not_blank(self, tmp_path: Path) -> None:
        """A bbox entirely outside the image is not blank (fail open)."""
        img = _make_white_png(tmp_path / "white.png", width=100, height=100)
        # Entirely outside (negative origin, negative size after clamp).
        assert RenderStage._is_blank_region(str(img), (-50, -50, 10, 10)) is False


# ---------------------------------------------------------------------------
# _load_region_metadata
# ---------------------------------------------------------------------------

class TestLoadRegionMetadata:
    def test_extracts_prob_and_bbox(self, tmp_path: Path) -> None:
        regions = [
            {
                "index": 0,
                "text": "hello",
                "lines": [[[10, 20], [110, 20], [110, 70], [10, 70]]],
                "prob": 0.9995,
            },
            {
                "index": 1,
                "text": "world",
                "lines": [[[5, 5], [50, 5], [50, 50], [5, 50]]],
                "prob": 0.20,
            },
        ]
        _write_artifact(tmp_path, page_idx=3, text_regions=regions)
        meta = RenderStage._load_region_metadata(tmp_path, page_idx=3)
        assert set(meta.keys()) == {0, 1}
        assert meta[0]["prob"] == pytest.approx(0.9995)
        assert meta[0]["bbox"] == (10, 20, 100, 50)
        assert meta[1]["prob"] == pytest.approx(0.20)
        assert meta[1]["bbox"] == (5, 5, 45, 45)

    def test_missing_prob_is_none(self, tmp_path: Path) -> None:
        regions = [{"index": 0, "text": "x", "lines": [[[0, 0], [10, 0], [10, 10], [0, 10]]]}]
        _write_artifact(tmp_path, page_idx=0, text_regions=regions)
        meta = RenderStage._load_region_metadata(tmp_path, page_idx=0)
        assert meta[0]["prob"] is None
        assert meta[0]["bbox"] == (0, 0, 10, 10)

    def test_missing_lines_bbox_none(self, tmp_path: Path) -> None:
        regions = [{"index": 0, "text": "x", "prob": 0.9}]
        _write_artifact(tmp_path, page_idx=0, text_regions=regions)
        meta = RenderStage._load_region_metadata(tmp_path, page_idx=0)
        assert meta[0]["prob"] == pytest.approx(0.9)
        assert meta[0]["bbox"] is None

    def test_missing_artifact_returns_empty(self, tmp_path: Path) -> None:
        assert RenderStage._load_region_metadata(tmp_path, page_idx=0) == {}

    def test_malformed_artifact_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "artifact-0000.json").write_text("{invalid json", encoding="utf-8")
        assert RenderStage._load_region_metadata(tmp_path, page_idx=0) == {}

    def test_falls_back_to_unsuffixed_artifact(self, tmp_path: Path) -> None:
        """When artifact-NNNN.json is absent, falls back to artifact.json."""
        regions = [{"index": 0, "text": "x", "lines": [[[0, 0], [10, 0], [10, 10], [0, 10]]], "prob": 0.8}]
        (tmp_path / "artifact.json").write_text(
            json.dumps({"version": 1, "text_regions": regions}) + "\n", encoding="utf-8"
        )
        meta = RenderStage._load_region_metadata(tmp_path, page_idx=5)
        assert 0 in meta
        assert meta[0]["prob"] == pytest.approx(0.8)


# ---------------------------------------------------------------------------
# _page_input_image_path
# ---------------------------------------------------------------------------

class TestPageInputImagePath:
    def test_resolves_path_for_matching_page(self) -> None:
        page = Page(
            page_id="page_3",
            page_index=3,
            image=PageImage(path="/tmp/page-004.png", width=500, height=500),
        )
        ctx = PipelineContext(project_config=ProjectConfig(), pages=[page])
        assert RenderStage._page_input_image_path(ctx, page_idx=3) == "/tmp/page-004.png"

    def test_returns_none_when_page_missing(self) -> None:
        ctx = PipelineContext(project_config=ProjectConfig(), pages=[])
        assert RenderStage._page_input_image_path(ctx, page_idx=0) is None

    def test_returns_none_when_path_empty(self) -> None:
        page = Page(page_id="page_0", page_index=0)  # default empty PageImage
        ctx = PipelineContext(project_config=ProjectConfig(), pages=[page])
        assert RenderStage._page_input_image_path(ctx, page_idx=0) is None


# ---------------------------------------------------------------------------
# _write_page_translations integration (blank + low-prob skip)
# ---------------------------------------------------------------------------

class TestWritePageTranslationsOcrGuard:
    """End-to-end tests of the guard through _write_page_translations."""

    def _make_context(
        self,
        page_idx: int,
        input_image_path: str,
        translations: list[TranslationCandidate],
    ) -> PipelineContext:
        page = Page(
            page_id=f"page_{page_idx}",
            page_index=page_idx,
            image=PageImage(path=input_image_path, width=500, height=500),
        )
        return PipelineContext(
            project_config=ProjectConfig(),
            pages=[page],
            translations=translations,
        )

    def test_footnotes_omitted_from_runtime_payload_by_default(self, tmp_path: Path) -> None:
        img = _make_text_png(tmp_path / "page-005.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=4, text_regions=[
            {
                "index": 0,
                "text": "real text",
                "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]],
                "prob": 0.95,
            },
        ])
        translation = TranslationCandidate(
            bubble_id="region-0004-0000",
            text="dialogue",
            footnotes=[
                FootnoteEntry(
                    original="term",
                    translation="note",
                    type="loanword",
                    explanation="explanation",
                )
            ],
        )
        ctx = self._make_context(page_idx=4, input_image_path=str(img), translations=[translation])

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=4)

        out = json.loads((tmp_path / "translations-0004.json").read_text(encoding="utf-8"))
        assert out["translations"] == [{"region_index": 0, "translation": "dialogue", "target_lang": "CHS"}]
        assert out["footnotes"] == []

    def test_footnotes_preserved_when_runtime_rendering_enabled(self, tmp_path: Path) -> None:
        img = _make_text_png(tmp_path / "page-005.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=4, text_regions=[
            {
                "index": 0,
                "text": "real text",
                "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]],
                "prob": 0.95,
            },
        ])
        translation = TranslationCandidate(
            bubble_id="region-0004-0000",
            text="dialogue",
            footnotes=[
                FootnoteEntry(
                    original="term",
                    translation="note",
                    type="loanword",
                    explanation="explanation",
                )
            ],
        )
        ctx = self._make_context(page_idx=4, input_image_path=str(img), translations=[translation])
        cfg = ProjectConfig(render_footnotes=True)

        RenderStage()._write_page_translations(tmp_path, ctx, cfg, page_idx=4)

        out = json.loads((tmp_path / "translations-0004.json").read_text(encoding="utf-8"))
        assert out["footnotes"] == [
            {
                "original": "term",
                "translation": "note",
                "type": "loanword",
                "explanation": "explanation",
            }
        ]

    def test_blank_region_skipped(self, tmp_path: Path) -> None:
        """A translation whose OCR region is on a blank/white area is skipped."""
        img = _make_white_png(tmp_path / "page-004.png", width=500, height=500)
        # Region 0 covers the whole white image → blank → skipped.
        _write_artifact(tmp_path, page_idx=3, text_regions=[
            {
                "index": 0,
                "text": "hallucinated",
                "lines": [[[0, 0], [500, 0], [500, 500], [0, 500]]],
                "prob": 0.9995,
            },
            {
                "index": 1,
                "text": "real",
                # A tiny region; will be clamped but still white → blank too.
                "lines": [[[10, 10], [20, 10], [20, 20], [10, 20]]],
                "prob": 0.99,
            },
        ])
        ctx = self._make_context(
            page_idx=3,
            input_image_path=str(img),
            translations=[
                TranslationCandidate(bubble_id="region-0003-0000", text="幻觉文本"),
                TranslationCandidate(bubble_id="region-0003-0001", text="真实文本"),
            ],
        )
        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=3)
        out = json.loads((tmp_path / "translations-0003.json").read_text(encoding="utf-8"))
        # Both regions are on pure white → both skipped.
        assert out["translations"] == []

    def test_text_region_kept(self, tmp_path: Path) -> None:
        """A translation whose OCR region has real text pixels is kept."""
        img = _make_text_png(tmp_path / "page-005.png", width=500, height=500)
        # Region 0 covers the text band (y 100..400) → not blank → kept.
        _write_artifact(tmp_path, page_idx=4, text_regions=[
            {
                "index": 0,
                "text": "real text",
                "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]],
                "prob": 0.95,
            },
        ])
        ctx = self._make_context(
            page_idx=4,
            input_image_path=str(img),
            translations=[TranslationCandidate(bubble_id="region-0004-0000", text="真实文本")],
        )
        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=4)
        out = json.loads((tmp_path / "translations-0004.json").read_text(encoding="utf-8"))
        assert len(out["translations"]) == 1
        assert out["translations"][0]["region_index"] == 0
        assert out["translations"][0]["translation"] == "真实文本"

    def test_low_prob_region_skipped(self, tmp_path: Path) -> None:
        """A region with prob below the threshold is skipped even on a non-blank image."""
        img = _make_text_png(tmp_path / "page-006.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=5, text_regions=[
            {
                "index": 0,
                "text": "publisher label",
                "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]],
                "prob": 0.20,  # below default 0.25
            },
        ])
        ctx = self._make_context(
            page_idx=5,
            input_image_path=str(img),
            translations=[TranslationCandidate(bubble_id="region-0005-0000", text="出版社")],
        )
        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=5)
        out = json.loads((tmp_path / "translations-0005.json").read_text(encoding="utf-8"))
        assert out["translations"] == []

    def test_low_prob_threshold_configurable(self, tmp_path: Path) -> None:
        """ocr_min_prob=0.0 disables prob filtering; a prob=0.20 region is kept."""
        img = _make_text_png(tmp_path / "page-007.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=6, text_regions=[
            {
                "index": 0,
                "text": "publisher label",
                "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]],
                "prob": 0.20,
            },
        ])
        ctx = self._make_context(
            page_idx=6,
            input_image_path=str(img),
            translations=[TranslationCandidate(bubble_id="region-0006-0000", text="出版社")],
        )
        RenderStage(ocr_min_prob=0.0)._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=6)
        out = json.loads((tmp_path / "translations-0006.json").read_text(encoding="utf-8"))
        assert len(out["translations"]) == 1

    def test_mixed_regions_skips_only_blank(self, tmp_path: Path) -> None:
        """When one region is blank and another has text, only the blank one is skipped."""
        # Left half white, right half has text.
        img = Image.new("RGB", (500, 500), (255, 255, 255))
        px = img.load()
        for y in range(0, 500):
            for x in range(250, 500, 3):
                px[x, y] = (0, 0, 0)
        img.save(tmp_path / "page-008.png")

        _write_artifact(tmp_path, page_idx=7, text_regions=[
            {
                "index": 0,
                "text": "blank area",
                "lines": [[[0, 0], [240, 0], [240, 500], [0, 500]]],  # left half → blank
                "prob": 0.99,
            },
            {
                "index": 1,
                "text": "real text",
                "lines": [[[260, 0], [500, 0], [500, 500], [260, 500]]],  # right half → text
                "prob": 0.99,
            },
        ])
        ctx = self._make_context(
            page_idx=7,
            input_image_path=str(tmp_path / "page-008.png"),
            translations=[
                TranslationCandidate(bubble_id="region-0007-0000", text="幻觉"),
                TranslationCandidate(bubble_id="region-0007-0001", text="真实"),
            ],
        )
        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=7)
        out = json.loads((tmp_path / "translations-0007.json").read_text(encoding="utf-8"))
        assert len(out["translations"]) == 1
        assert out["translations"][0]["region_index"] == 0
        assert out["translations"][0]["translation"] == "真实"

        artifact = json.loads((tmp_path / "artifact-0007.json").read_text(encoding="utf-8"))
        assert len(artifact["text_regions"]) == 1
        assert artifact["text_regions"][0]["text"] == "real text"
        assert artifact["text_regions"][0]["index"] == 0

    def test_no_artifact_keeps_all_translations(self, tmp_path: Path) -> None:
        """When the artifact file is missing, no filtering occurs (fail open)."""
        img = _make_text_png(tmp_path / "page-009.png", width=500, height=500)
        # No artifact written.
        ctx = self._make_context(
            page_idx=8,
            input_image_path=str(img),
            translations=[TranslationCandidate(bubble_id="region-0008-0000", text="保留")],
        )
        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=8)
        out = json.loads((tmp_path / "translations-0008.json").read_text(encoding="utf-8"))
        assert len(out["translations"]) == 1
        assert out["translations"][0]["translation"] == "保留"

    def test_no_input_image_keeps_all_translations(self, tmp_path: Path) -> None:
        """When the input image path is unavailable, blank check is skipped (fail open)."""
        _write_artifact(tmp_path, page_idx=0, text_regions=[
            {
                "index": 0,
                "text": "x",
                "lines": [[[0, 0], [500, 0], [500, 500], [0, 500]]],
                "prob": 0.99,
            },
        ])
        page = Page(page_id="page_0", page_index=0)  # no image path
        ctx = PipelineContext(project_config=ProjectConfig(), pages=[page], translations=[
            TranslationCandidate(bubble_id="region-0000-0000", text="保留"),
        ])
        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=0)
        out = json.loads((tmp_path / "translations-0000.json").read_text(encoding="utf-8"))
        assert len(out["translations"]) == 1

    def test_no_prob_in_artifact_keeps_region(self, tmp_path: Path) -> None:
        """A region without a prob field is not filtered by the prob threshold."""
        img = _make_text_png(tmp_path / "page.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=0, text_regions=[
            {"index": 0, "text": "noprob", "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]]},
        ])
        ctx = self._make_context(
            page_idx=0,
            input_image_path=str(img),
            translations=[TranslationCandidate(bubble_id="region-0000-0000", text="kept")],
        )
        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=0)
        out = json.loads((tmp_path / "translations-0000.json").read_text(encoding="utf-8"))
        assert len(out["translations"]) == 1
        assert out["translations"][0]["region_index"] == 0

    def test_existing_empty_artifact_drops_region_translations(self, tmp_path: Path) -> None:
        """If an artifact explicitly has no render seats, do not emit region
        translations whose indices cannot be rendered. This prevents payloads
        like page-010's empty artifact plus translations 0..8."""
        img = _make_text_png(tmp_path / "page.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=9, text_regions=[])
        ctx = self._make_context(
            page_idx=9,
            input_image_path=str(img),
            translations=[TranslationCandidate(bubble_id="region-0009-0000", text="missing")],
        )

        RenderStage(pin_artifacts=False)._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=9)

        out = json.loads((tmp_path / "translations-0009.json").read_text(encoding="utf-8"))
        assert out["translations"] == []

    def test_empty_final_translations_clear_artifact_and_restore_inpainted_image(self, tmp_path: Path) -> None:
        original = Image.new("RGB", (100, 100), (20, 40, 60))
        original.save(tmp_path / "page-001.png")
        Image.new("RGB", (100, 100), (255, 255, 255)).save(tmp_path / "inpainted-0000.png")
        _write_artifact(tmp_path, page_idx=0, text_regions=[
            {
                "index": 0,
                "text": "CoverDesign",
                "lines": [[[0, 0], [100, 0], [100, 100], [0, 100]]],
                "prob": 0.99,
            },
        ])
        ctx = self._make_context(
            page_idx=0,
            input_image_path=str(tmp_path / "page-001.png"),
            translations=[TranslationCandidate(bubble_id="region-0000-0000", text="cover")],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=0)

        out = json.loads((tmp_path / "translations-0000.json").read_text(encoding="utf-8"))
        artifact = json.loads((tmp_path / "artifact-0000.json").read_text(encoding="utf-8"))
        restored = Image.open(tmp_path / "inpainted-0000.png").convert("RGB")
        assert out["translations"] == []
        assert out["footnotes"] == []
        assert artifact["text_regions"] == []
        assert restored.getpixel((50, 50)) == (20, 40, 60)

    def test_page_004_toc_hallucination_scenario(self, tmp_path: Path) -> None:
        """Reproduces the e2e bug from data/output/test-pdf-10pages-e2e-test.

        On page-004 (TOC), OCR detected 'これが人を愛し 慈しみ信じた者の末路さ'
        (prob=0.9995) on a PURE WHITE area (mean=255, std=0). The high prob does
        NOT save it — the blank-region check catches it. The real chapter title
        '化け狐' (prob=0.99996) on a dark text block is kept.
        """
        import numpy as np
        # White page with a dark text block where region 1 lands (化け狐 title).
        arr = np.full((600, 600, 3), 255, dtype=np.uint8)
        arr[400:500, 400:500] = (10, 10, 10)  # dark block for region 1
        img = tmp_path / "page-004.png"
        Image.fromarray(arr).save(img)

        # Region 0: hallucinated dialogue on white TOC area (high prob, blank).
        # Region 1: real chapter title on the dark block.
        _write_artifact(tmp_path, page_idx=3, text_regions=[
            {
                "index": 0,
                "text": "これが人を愛し 慈しみ信じた者の末路さ",
                "lines": [[[50, 50], [150, 50], [150, 150], [50, 150]]],
                "prob": 0.9995,
            },
            {
                "index": 1,
                "text": "化け狐",
                "lines": [[[400, 400], [500, 400], [500, 500], [400, 500]]],
                "prob": 0.99996,
            },
        ])
        ctx = self._make_context(
            page_idx=3,
            input_image_path=str(img),
            translations=[
                TranslationCandidate(bubble_id="region-0003-0000", text="这就是爱着人的结局"),
                TranslationCandidate(bubble_id="region-0003-0001", text="狐妖"),
            ],
        )
        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=3)
        out = json.loads((tmp_path / "translations-0003.json").read_text(encoding="utf-8"))
        # Hallucinated region 0 dropped; real region 1 survives.
        assert [t["region_index"] for t in out["translations"]] == [0]
        assert out["translations"][0]["translation"] == "狐妖"


# ---------------------------------------------------------------------------
# Vision region injection (_inject_vision_regions + _write_page_translations)
# ---------------------------------------------------------------------------


class TestVisionRegionInjection:
    """Vision render seats are injected only when OCR did not cover that bbox.

    Runtime OCR geometry is authoritative for OCR-detected bubbles. Vision
    bboxes that overlap OCR regions are skipped, while non-overlapping vision
    bubbles get render seats so mixed OCR+vision pages do not drop them.
    """

    def _make_ctx_with_vision(
        self,
        page_idx: int,
        input_image_path: str,
        region_translations: list[TranslationCandidate],
        vision_bubbles: list[Bubble],
        vision_translations: list[TranslationCandidate],
    ) -> PipelineContext:
        page = Page(
            page_id=f"page_{page_idx}",
            page_index=page_idx,
            image=PageImage(path=input_image_path, width=500, height=500),
            bubbles=vision_bubbles,
        )
        return PipelineContext(
            project_config=ProjectConfig(),
            pages=[page],
            translations=region_translations + vision_translations,
        )

    def test_vision_bubble_gets_appended_region_seat_for_empty_ocr_artifact(self, tmp_path: Path) -> None:
        img = _make_text_png(tmp_path / "page-001.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=0, text_regions=[])
        vision_bubble = Bubble(
            bubble_id="vision-0000-0000",
            bbox=BoundingBox(x=10, y=150, width=80, height=30),
            source_text="vision",
            detection_source="vision",
        )
        ctx = self._make_ctx_with_vision(
            page_idx=0,
            input_image_path=str(img),
            region_translations=[],
            vision_bubbles=[vision_bubble],
            vision_translations=[TranslationCandidate(bubble_id="vision-0000-0000", text="VISION")],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=0)

        artifact = json.loads((tmp_path / "artifact-0000.json").read_text(encoding="utf-8"))
        assert len(artifact["text_regions"]) == 1
        vision_region = artifact["text_regions"][0]
        assert vision_region["index"] == 0
        assert vision_region["lines"] == [[[10.0, 150.0], [90.0, 150.0], [90.0, 180.0], [10.0, 180.0]]]

        out = json.loads((tmp_path / "translations-0000.json").read_text(encoding="utf-8"))
        assert out["translations"] == [
            {"region_index": 0, "translation": "VISION", "target_lang": "CHS"}
        ]

    def test_only_non_overlapping_vision_regions_injected_when_ocr_regions_exist(self, tmp_path: Path) -> None:
        img = _make_text_png(tmp_path / "page-002.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=1, text_regions=[
            {"index": 0, "text": "ocr0",
             "lines": [[[0, 100], [250, 100], [250, 400], [0, 400]]], "prob": 0.9},
            {"index": 1, "text": "ocr1",
             "lines": [[[250, 100], [500, 100], [500, 400], [250, 400]]], "prob": 0.9},
        ])
        overlapping_vision = Bubble(
            bubble_id="vision-0001-0000",
            bbox=BoundingBox(x=10, y=150, width=80, height=30),
            source_text="vision",
            detection_source="vision",
        )
        uncovered_vision = Bubble(
            bubble_id="vision-0001-0001",
            bbox=BoundingBox(x=10, y=10, width=80, height=30),
            source_text="uncovered",
            detection_source="vision",
        )
        ctx = self._make_ctx_with_vision(
            page_idx=1,
            input_image_path=str(img),
            region_translations=[
                TranslationCandidate(bubble_id="region-0001-0000", text="OCR0"),
                TranslationCandidate(bubble_id="region-0001-0001", text="OCR1"),
            ],
            vision_bubbles=[overlapping_vision, uncovered_vision],
            vision_translations=[
                TranslationCandidate(bubble_id="vision-0001-0000", text="OVERLAP"),
                TranslationCandidate(bubble_id="vision-0001-0001", text="VISION"),
            ],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=1)

        artifact = json.loads((tmp_path / "artifact-0001.json").read_text(encoding="utf-8"))
        assert len(artifact["text_regions"]) == 3
        assert artifact["text_regions"][0]["text"] == "ocr0"
        assert artifact["text_regions"][1]["text"] == "ocr1"
        assert artifact["text_regions"][2]["source"] == "vision"
        assert artifact["text_regions"][2]["bubble_id"] == "vision-0001-0001"

        out = json.loads((tmp_path / "translations-0001.json").read_text(encoding="utf-8"))
        by_idx = {t["region_index"]: t["translation"] for t in out["translations"]}
        assert by_idx == {0: "OCR0", 1: "OCR1", 2: "VISION"}

    def test_same_source_vision_region_skipped_even_when_bbox_misses_ocr(self, tmp_path: Path) -> None:
        img = _make_text_png(tmp_path / "page-002.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=1, text_regions=[
            {"index": 0, "text": "これが人を愛し 慈しみ信じた者の末路さ",
             "lines": [[[250, 100], [500, 100], [500, 400], [250, 400]]], "prob": 0.9},
        ])
        duplicate_vision = Bubble(
            bubble_id="vision-0001-0000",
            bbox=BoundingBox(x=10, y=10, width=80, height=30),
            source_text="これが人を愛し慈しみ信じた者の末路さ",
            detection_source="vision",
        )
        ctx = self._make_ctx_with_vision(
            page_idx=1,
            input_image_path=str(img),
            region_translations=[
                TranslationCandidate(bubble_id="region-0001-0000", text="OCR"),
            ],
            vision_bubbles=[duplicate_vision],
            vision_translations=[
                TranslationCandidate(bubble_id="vision-0001-0000", text="DUP"),
            ],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=1)

        artifact = json.loads((tmp_path / "artifact-0001.json").read_text(encoding="utf-8"))
        assert len(artifact["text_regions"]) == 1
        out = json.loads((tmp_path / "translations-0001.json").read_text(encoding="utf-8"))
        assert out["translations"] == [
            {"region_index": 0, "translation": "OCR", "target_lang": "CHS"}
        ]

    def test_near_same_source_vision_region_skipped_for_punctuation_drift(self, tmp_path: Path) -> None:
        img = _make_text_png(tmp_path / "page-007.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=6, text_regions=[
            {"index": 0, "text": "きっとあたしと同じだよ――…",
             "lines": [[[250, 100], [500, 100], [500, 400], [250, 400]]], "prob": 0.892},
        ])
        duplicate_vision = Bubble(
            bubble_id="vision-0006-0000",
            bbox=BoundingBox(x=10, y=10, width=80, height=30),
            source_text="きっとあたしと同じだよ……！",
            detection_source="vision",
        )
        ctx = self._make_ctx_with_vision(
            page_idx=6,
            input_image_path=str(img),
            region_translations=[
                TranslationCandidate(bubble_id="region-0006-0000", text="OCR"),
            ],
            vision_bubbles=[duplicate_vision],
            vision_translations=[
                TranslationCandidate(bubble_id="vision-0006-0000", text="LEAK"),
            ],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=6)

        artifact = json.loads((tmp_path / "artifact-0006.json").read_text(encoding="utf-8"))
        assert len(artifact["text_regions"]) == 1
        out = json.loads((tmp_path / "translations-0006.json").read_text(encoding="utf-8"))
        assert out["translations"] == [
            {"region_index": 0, "translation": "OCR", "target_lang": "CHS"}
        ]

    def test_short_name_vision_region_skipped_for_near_duplicate_ocr_name(self, tmp_path: Path) -> None:
        img = _make_text_png(tmp_path / "page-009.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=8, text_regions=[
            {"index": 0, "text": "\u7f8e\u80e1\u3061\u3083\u3093",
             "lines": [[[350, 50], [450, 50], [450, 200], [350, 200]]], "prob": 0.999},
        ])
        duplicate_vision = Bubble(
            bubble_id="vision-0008-0001",
            bbox=BoundingBox(x=100, y=180, width=90, height=70),
            source_text="\u7f8e\u6e56\u3061\u3083\u3093",
            detection_source="vision",
        )
        ctx = self._make_ctx_with_vision(
            page_idx=8,
            input_image_path=str(img),
            region_translations=[
                TranslationCandidate(bubble_id="region-0008-0000", text="OCR"),
            ],
            vision_bubbles=[duplicate_vision],
            vision_translations=[
                TranslationCandidate(bubble_id="vision-0008-0001", text="LEAK"),
            ],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=8)

        artifact = json.loads((tmp_path / "artifact-0008.json").read_text(encoding="utf-8"))
        assert len(artifact["text_regions"]) == 1
        out = json.loads((tmp_path / "translations-0008.json").read_text(encoding="utf-8"))
        assert out["translations"] == [
            {"region_index": 0, "translation": "OCR", "target_lang": "CHS"}
        ]

    def test_vision_bubble_zero_bbox_skipped(self, tmp_path: Path) -> None:
        img = _make_text_png(tmp_path / "page-003.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=2, text_regions=[])
        vision_bubble = Bubble(
            bubble_id="vision-0002-0000",
            bbox=BoundingBox(x=0, y=0, width=0, height=0),
            source_text="no geometry",
            detection_source="vision",
        )
        ctx = self._make_ctx_with_vision(
            page_idx=2,
            input_image_path=str(img),
            region_translations=[],
            vision_bubbles=[vision_bubble],
            vision_translations=[TranslationCandidate(bubble_id="vision-0002-0000", text="NOSEAT")],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=2)

        artifact = json.loads((tmp_path / "artifact-0002.json").read_text(encoding="utf-8"))
        assert artifact["text_regions"] == []
        out = json.loads((tmp_path / "translations-0002.json").read_text(encoding="utf-8"))
        assert out["translations"] == []

    def test_vision_sfx_bubble_is_not_injected(self, tmp_path: Path) -> None:
        img = _make_text_png(tmp_path / "page-009.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=8, text_regions=[])
        sfx_bubble = Bubble(
            bubble_id="vision-0008-0001",
            bbox=BoundingBox(x=40, y=120, width=80, height=180),
            source_text="ガタン",
            detection_source="vision",
            box_type="sfx",
        )
        ctx = self._make_ctx_with_vision(
            page_idx=8,
            input_image_path=str(img),
            region_translations=[],
            vision_bubbles=[sfx_bubble],
            vision_translations=[TranslationCandidate(bubble_id="vision-0008-0001", text="哐啷")],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=8)

        artifact = json.loads((tmp_path / "artifact-0008.json").read_text(encoding="utf-8"))
        out = json.loads((tmp_path / "translations-0008.json").read_text(encoding="utf-8"))
        assert artifact["text_regions"] == []
        assert out["translations"] == []

    def test_contents_page_vision_entries_are_renderable(self, tmp_path: Path) -> None:
        img = Image.new("RGB", (500, 500), (255, 255, 255))
        px = img.load()
        # Page-004 has short red page-number/ornament clusters outside the TOC
        # body. They must not be consumed before the real vertical title column.
        for y in range(420, 455):
            for x in range(40, 95):
                px[x, y] = (220, 40, 55)
        for x0 in (320, 220):
            for y in range(180, 360):
                for x in range(x0, x0 + 18):
                    px[x, y] = (220, 40, 55)
        img_path = tmp_path / "page-004.png"
        img.save(img_path)
        _write_artifact(tmp_path, page_idx=3, text_regions=[])
        contents_marker = Bubble(
            bubble_id="vision-0003-0000",
            bbox=BoundingBox(x=150, y=90, width=120, height=30),
            source_text="CONTENTS",
            detection_source="vision",
            box_type="other",
        )
        toc_entry = Bubble(
            bubble_id="vision-0003-0001",
            bbox=BoundingBox(x=210, y=170, width=40, height=160),
            source_text="昔日の足音 003",
            detection_source="vision",
            box_type="other",
        )
        ctx = self._make_ctx_with_vision(
            page_idx=3,
            input_image_path=str(img_path),
            region_translations=[],
            vision_bubbles=[contents_marker, toc_entry],
            vision_translations=[
                TranslationCandidate(bubble_id="vision-0003-0001", text="往日的足音 003"),
            ],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=3)

        artifact = json.loads((tmp_path / "artifact-0003.json").read_text(encoding="utf-8"))
        out = json.loads((tmp_path / "translations-0003.json").read_text(encoding="utf-8"))
        assert len(artifact["text_regions"]) == 1
        assert artifact["text_regions"][0]["source"] == "vision"
        assert artifact["text_regions"][0]["bubble_id"] == "vision-0003-0001"
        assert artifact["text_regions"][0]["lines"][0][0][0] >= 300
        assert out["footnotes"] == []
        assert out["translations"] == [
            {"region_index": 0, "translation": "往日的足音 003", "target_lang": "CHS"}
        ]

    def test_contents_red_text_columns_ignore_short_noise(self, tmp_path: Path) -> None:
        img = Image.new("RGB", (800, 900), (255, 255, 255))
        px = img.load()
        for y in range(720, 760):
            for x in range(60, 140):
                px[x, y] = (220, 40, 55)
        for x0 in (610, 470, 330):
            for y in range(280, 760):
                for x in range(x0, x0 + 22):
                    px[x, y] = (220, 40, 55)
        img_path = tmp_path / "contents.png"
        img.save(img_path)

        columns = RenderStage._contents_red_text_columns(str(img_path))

        assert len(columns) == 3
        assert [round(box[0]) for box in columns] == [604, 464, 324]

    def test_contents_page_reuses_existing_ocr_seats(self, tmp_path: Path) -> None:
        img = Image.new("RGB", (800, 900), (255, 255, 255))
        px = img.load()
        for x0 in (610, 470):
            for y in range(280, 760):
                for x in range(x0, x0 + 22):
                    px[x, y] = (220, 40, 55)
        img_path = tmp_path / "page-004.png"
        img.save(img_path)
        _write_artifact(tmp_path, page_idx=3, text_regions=[
            {"index": 0, "text": "toc-right", "lines": [[[610, 280], [632, 280], [632, 760], [610, 760]]]},
            {"index": 1, "text": "toc-left", "lines": [[[470, 280], [492, 280], [492, 760], [470, 760]]]},
        ])
        contents_marker = Bubble(
            bubble_id="vision-0003-0000",
            bbox=BoundingBox(x=150, y=90, width=120, height=30),
            source_text="CONTENTS",
            detection_source="vision",
            box_type="other",
        )
        right_entry = Bubble(
            bubble_id="vision-0003-0001",
            bbox=BoundingBox(x=200, y=100, width=40, height=160),
            source_text="entry-right",
            detection_source="vision",
            box_type="other",
        )
        left_entry = Bubble(
            bubble_id="vision-0003-0002",
            bbox=BoundingBox(x=120, y=100, width=40, height=160),
            source_text="entry-left",
            detection_source="vision",
            box_type="other",
        )
        ctx = self._make_ctx_with_vision(
            page_idx=3,
            input_image_path=str(img_path),
            region_translations=[],
            vision_bubbles=[contents_marker, right_entry, left_entry],
            vision_translations=[
                TranslationCandidate(bubble_id="vision-0003-0001", text="RIGHT"),
                TranslationCandidate(bubble_id="vision-0003-0002", text="LEFT"),
            ],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=3)

        artifact = json.loads((tmp_path / "artifact-0003.json").read_text(encoding="utf-8"))
        out = json.loads((tmp_path / "translations-0003.json").read_text(encoding="utf-8"))
        assert len(artifact["text_regions"]) == 2
        assert out["translations"] == [
            {"region_index": 0, "translation": "RIGHT", "target_lang": "CHS"},
            {"region_index": 1, "translation": "LEFT", "target_lang": "CHS"},
        ]
        assert out["footnotes"] == []

    def test_contents_page_keeps_wide_ocr_title_entries(self, tmp_path: Path) -> None:
        img = Image.new("RGB", (800, 900), (255, 255, 255))
        px = img.load()
        for y in range(260, 620):
            for x in range(560, 700):
                px[x, y] = (220, 40, 55)
        img_path = tmp_path / "page-004.png"
        img.save(img_path)
        _write_artifact(tmp_path, page_idx=3, text_regions=[
            {
                "index": 0,
                "text": "32 chapter title 003",
                "lines": [[[560, 260], [700, 260], [700, 620], [560, 620]]],
                "prob": 0.99,
            },
            {
                "index": 1,
                "text": "CONTENTS",
                "lines": [[[300, 150], [450, 150], [450, 190], [300, 190]]],
                "prob": 0.99,
            },
        ])
        page = Page(
            page_id="page_3",
            page_index=3,
            image=PageImage(path=str(img_path), width=800, height=900),
            bubbles=[
                Bubble(bubble_id="region-0003-0000", source_text="32 chapter title 003"),
                Bubble(bubble_id="region-0003-0001", source_text="CONTENTS"),
            ],
        )
        ctx = PipelineContext(
            project_config=ProjectConfig(),
            pages=[page],
            translations=[
                TranslationCandidate(bubble_id="region-0003-0000", text="Chapter 32 Title 003"),
                TranslationCandidate(bubble_id="region-0003-0001", text="Contents"),
            ],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=3)

        out = json.loads((tmp_path / "translations-0003.json").read_text(encoding="utf-8"))
        assert out["translations"] == [
            {"region_index": 0, "translation": "Chapter 32 Title 003", "target_lang": "CHS"},
        ]
        assert out["footnotes"] == []

    def test_contents_chapter_number_uses_following_vision_title(self, tmp_path: Path) -> None:
        img = Image.new("RGB", (800, 900), (255, 255, 255))
        px = img.load()
        for y in range(260, 620):
            for x in range(500, 560):
                px[x, y] = (220, 40, 55)
        img_path = tmp_path / "page-004.png"
        img.save(img_path)
        _write_artifact(tmp_path, page_idx=3, text_regions=[
            {
                "index": 0,
                "text": "34話",
                "lines": [[[500, 260], [560, 260], [560, 620], [500, 620]]],
                "prob": 0.99,
            },
            {
                "index": 1,
                "text": "CONTENTS",
                "lines": [[[250, 120], [380, 120], [380, 150], [250, 150]]],
                "prob": 0.99,
            },
        ])
        page = Page(
            page_id="page_3",
            page_index=3,
            image=PageImage(path=str(img_path), width=800, height=900),
            bubbles=[
                Bubble(bubble_id="region-0003-0000", source_text="34話"),
                Bubble(
                    bubble_id="vision-0003-0003",
                    source_text="34話",
                    detection_source="vision",
                    box_type="other",
                ),
                Bubble(
                    bubble_id="vision-0003-0004",
                    source_text="慟愧の鞭",
                    detection_source="vision",
                    box_type="other",
                ),
            ],
        )
        ctx = PipelineContext(
            project_config=ProjectConfig(),
            pages=[page],
            translations=[
                TranslationCandidate(bubble_id="region-0003-0000", text="第34话"),
                TranslationCandidate(bubble_id="region-0003-0001", text="目录"),
                TranslationCandidate(bubble_id="vision-0003-0003", text="第34话"),
                TranslationCandidate(bubble_id="vision-0003-0004", text="恸愧之鞭"),
            ],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=3)

        out = json.loads((tmp_path / "translations-0003.json").read_text(encoding="utf-8"))
        assert out["translations"] == [
            {"region_index": 0, "translation": "第34话 恸愧之鞭", "target_lang": "CHS"},
        ]

    def test_no_vision_bubbles_is_noop(self, tmp_path: Path) -> None:
        img = _make_text_png(tmp_path / "page-004.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=3, text_regions=[
            {"index": 0, "text": "ocr0",
             "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]], "prob": 0.9},
        ])
        page = Page(
            page_id="page_3",
            page_index=3,
            image=PageImage(path=str(img), width=500, height=500),
            bubbles=[],
        )
        ctx = PipelineContext(
            project_config=ProjectConfig(),
            pages=[page],
            translations=[TranslationCandidate(bubble_id="region-0003-0000", text="OCR")],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=3)

        artifact = json.loads((tmp_path / "artifact-0003.json").read_text(encoding="utf-8"))
        assert len(artifact["text_regions"]) == 1

    def test_vision_region_on_blank_area_skipped_for_contents_pages(self, tmp_path: Path) -> None:
        img = _make_white_png(tmp_path / "page-005.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=4, text_regions=[])
        vision_bubble = Bubble(
            bubble_id="vision-0004-0000",
            bbox=BoundingBox(x=10, y=150, width=80, height=30),
            source_text="CONTENTS",
            detection_source="vision",
        )
        ctx = self._make_ctx_with_vision(
            page_idx=4,
            input_image_path=str(img),
            region_translations=[],
            vision_bubbles=[vision_bubble],
            vision_translations=[TranslationCandidate(bubble_id="vision-0004-0000", text="CONTENTS")],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=4)

        out = json.loads((tmp_path / "translations-0004.json").read_text(encoding="utf-8"))
        assert out["translations"] == []

    def test_existing_contents_page_ocr_regions_render_only_title_columns(self, tmp_path: Path) -> None:
        img = Image.new("RGB", (500, 500), (255, 255, 255))
        px = img.load()
        for y in range(180, 420):
            for x in range(260, 310):
                px[x, y] = (220, 40, 55)
        img_path = tmp_path / "page-004.png"
        img.save(img_path)
        _write_artifact(tmp_path, page_idx=3, text_regions=[
            {"index": 0, "text": "32Ԓ ���դ����� 0",
             "lines": [[[260, 180], [310, 180], [310, 420], [260, 420]]], "prob": 0.98},
            {"index": 1, "text": "CONTENTS",
             "lines": [[[150, 150], [220, 150], [220, 170], [150, 170]]], "prob": 0.99},
            {"index": 2, "text": "059",
             "lines": [[[120, 180], [130, 180], [130, 200], [120, 200]]], "prob": 0.99},
            {"index": 3, "text": "afterword",
             "lines": [[[40, 40], [60, 40], [60, 180], [40, 180]]], "prob": 0.99},
        ])
        page = Page(
            page_id="page_3",
            page_index=3,
            image=PageImage(path=str(img_path), width=500, height=500),
            bubbles=[],
        )
        ctx = PipelineContext(
            project_config=ProjectConfig(),
            pages=[page],
            translations=[
                TranslationCandidate(bubble_id="region-0003-0000", text="Chapter 32"),
                TranslationCandidate(bubble_id="region-0003-0001", text="Contents"),
                TranslationCandidate(bubble_id="region-0003-0002", text="059"),
                TranslationCandidate(bubble_id="region-0003-0003", text="Afterword"),
            ],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=3)

        out = json.loads((tmp_path / "translations-0003.json").read_text(encoding="utf-8"))
        assert out["translations"] == [
            {"region_index": 0, "translation": "Chapter 32", "target_lang": "CHS"},
        ]

    def test_chapter_marker_is_not_rendered_but_title_text_is_preserved(self, tmp_path: Path) -> None:
        img = _make_text_png(tmp_path / "page-008.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=7, text_regions=[
            {"index": 0, "text": "昔日の足音",
             "lines": [[[0, 100], [200, 100], [200, 400], [0, 400]]], "prob": 0.99},
            {"index": 1, "source": "vision", "bubble_id": "vision-0007-0000", "text": "32話",
             "lines": [[[250, 100], [330, 100], [330, 180], [250, 180]]], "prob": None},
        ])
        page = Page(
            page_id="page_7",
            page_index=7,
            image=PageImage(path=str(img), width=500, height=500),
            bubbles=[Bubble(
                bubble_id="vision-0007-0000",
                bbox=BoundingBox(x=250, y=100, width=80, height=80),
                source_text="32話",
                detection_source="vision",
            )],
        )
        ctx = PipelineContext(
            project_config=ProjectConfig(),
            pages=[page],
            translations=[
                TranslationCandidate(bubble_id="region-0007-0000", text="Chapter title"),
                TranslationCandidate(bubble_id="vision-0007-0000", text="Episode number"),
            ],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=7)

        out = json.loads((tmp_path / "translations-0007.json").read_text(encoding="utf-8"))
        assert out["translations"] == [
            {"region_index": 0, "translation": "Chapter title", "target_lang": "CHS"}
        ]

    def test_single_ocr_chapter_title_region_is_rendered_by_box_type(self, tmp_path: Path) -> None:
        img = _make_text_png(tmp_path / "page-008.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=7, text_regions=[
            {"index": 0, "text": "���դ�����",
             "lines": [[[300, 80], [320, 80], [320, 180], [300, 180]]], "prob": 0.99},
        ])
        page = Page(
            page_id="page_7",
            page_index=7,
            image=PageImage(path=str(img), width=500, height=500),
            bubbles=[Bubble(
                bubble_id="region-0007-0000",
                source_text="���դ�����",
                box_type="chapter_title",
            )],
        )
        ctx = PipelineContext(
            project_config=ProjectConfig(),
            pages=[page],
            translations=[TranslationCandidate(bubble_id="region-0007-0000", text="Chapter title")],
        )

        RenderStage()._write_page_translations(tmp_path, ctx, ProjectConfig(), page_idx=7)

        out = json.loads((tmp_path / "translations-0007.json").read_text(encoding="utf-8"))
        assert out["translations"] == [
            {"region_index": 0, "translation": "Chapter title", "target_lang": "CHS"}
        ]

    def test_injection_idempotent_across_reruns(self, tmp_path: Path) -> None:
        img = _make_text_png(tmp_path / "page-006.png", width=500, height=500)
        vision_bubble = Bubble(
            bubble_id="vision-0000-0000",
            bbox=BoundingBox(x=10, y=150, width=80, height=30),
            source_text="v",
            detection_source="vision",
        )

        _write_artifact(tmp_path, page_idx=0, text_regions=[
            {"index": 0, "text": "ocr",
             "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]], "prob": 0.9},
        ])
        ctx = self._make_ctx_with_vision(
            page_idx=0,
            input_image_path=str(img),
            region_translations=[TranslationCandidate(bubble_id="region-0000-0000", text="OCR")],
            vision_bubbles=[vision_bubble],
            vision_translations=[TranslationCandidate(bubble_id="vision-0000-0000", text="VISION")],
        )
        RenderStage(pin_artifacts=False)._write_page_translations(tmp_path, ctx, ProjectConfig(), 0)
        a0 = json.loads((tmp_path / "artifact-0000.json").read_text(encoding="utf-8"))
        assert len(a0["text_regions"]) == 1

        payload2 = tmp_path / "p2"
        payload2.mkdir()
        _write_artifact(payload2, page_idx=0, text_regions=[])
        img2 = _make_text_png(payload2 / "page-006.png", width=500, height=500)
        page2 = Page(
            page_id="p0",
            page_index=0,
            image=PageImage(path=str(img2), width=500, height=500),
            bubbles=[vision_bubble],
        )
        ctx2 = PipelineContext(
            project_config=ProjectConfig(),
            pages=[page2],
            translations=[TranslationCandidate(bubble_id="vision-0000-0000", text="VISION")],
        )
        RenderStage(pin_artifacts=True)._write_page_translations(payload2, ctx2, ProjectConfig(), 0)
        a1 = json.loads((payload2 / "artifact-0000.json").read_text(encoding="utf-8"))
        assert len(a1["text_regions"]) == 1
        RenderStage(pin_artifacts=True)._write_page_translations(payload2, ctx2, ProjectConfig(), 0)
        a2 = json.loads((payload2 / "artifact-0000.json").read_text(encoding="utf-8"))
        assert len(a2["text_regions"]) == 1

    def test_stale_wrong_page_pin_replaced_when_current_artifact_matches_page_source(self, tmp_path: Path) -> None:
        img = _make_text_png(tmp_path / "page-007.png", width=500, height=500)
        cfg = ProjectConfig(working_dir=str(tmp_path / "project"))
        pin_dir = Path(cfg.working_dir) / ".mga_cache"
        pin_dir.mkdir(parents=True)

        from mga.runtime_bridge.artifact_cache import ArtifactPin, image_sha256

        ArtifactPin(pin_dir / "artifact-pin.json").put(image_sha256(img), {
            "version": 1,
            "page_index": 0,
            "text_regions": [
                {"index": 0, "text": "wrong-page", "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]]},
            ],
            "render_config": {},
            "image_shape": [500, 500, 3],
        })
        _write_artifact(tmp_path, page_idx=0, text_regions=[
            {"index": 0, "text": "current-page", "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]]},
        ])
        page = Page(
            page_id="page_0",
            page_index=0,
            image=PageImage(path=str(img), width=500, height=500),
            bubbles=[Bubble(bubble_id="region-0000-0000", source_text="current-page")],
        )
        ctx = PipelineContext(
            project_config=cfg,
            pages=[page],
            translations=[TranslationCandidate(bubble_id="region-0000-0000", text="CURRENT")],
        )

        RenderStage(pin_artifacts=True)._write_page_translations(tmp_path, ctx, cfg, 0)

        artifact = json.loads((tmp_path / "artifact-0000.json").read_text(encoding="utf-8"))
        assert artifact["text_regions"][0]["text"] == "current-page"
        stored = ArtifactPin(pin_dir / "artifact-pin.json").get(image_sha256(img))
        assert stored["text_regions"][0]["text"] == "current-page"


class TestExtractRenderTextLeak:
    """The QA re-translate path can emit markdown labels (e.g.
    '**Corrected Translation:**') into stored translations. _extract_render_text
    must strip them so they never render."""

    def test_strips_corrected_translation_markdown_label(self) -> None:
        raw = "**Corrected Translation:**  \n第35话 是记住光的东西"
        assert RenderStage._extract_render_text(raw) == "第35话 是记住光的东西"

    def test_strips_translation_markdown_label_same_line(self) -> None:
        assert RenderStage._extract_render_text("**Translation:** 你好") == "你好"

    def test_strips_plain_english_label(self) -> None:
        assert RenderStage._extract_render_text("Translation: 你好") == "你好"
        assert RenderStage._extract_render_text("Corrected Translation: 再见") == "再见"

    def test_strips_cjk_label(self) -> None:
        assert RenderStage._extract_render_text("**译文：** 你好") == "你好"
        assert RenderStage._extract_render_text("修正翻译：你好") == "你好"

    def test_preserves_normal_dialogue(self) -> None:
        assert RenderStage._extract_render_text("这就是爱着人的结局") == "这就是爱着人的结局"
        # Dialogue that happens to contain '**' mid-string is left intact.
        assert "**" not in RenderStage._extract_render_text("普通对话不需要星号")

    def test_strips_label_inside_json_text_field(self) -> None:
        raw = '{"text": "**Corrected Translation:**\\n你好", "rationale": ""}'
        assert RenderStage._extract_render_text(raw) == "你好"

    def test_empty_and_whitespace(self) -> None:
        assert RenderStage._extract_render_text("") == ""
        assert RenderStage._extract_render_text("   ") == ""


# ---------------------------------------------------------------------------
# Render purity: output is a deterministic, per-page-isolated function of
# (input image I_n, translation T_n) — the project goal. The runtime artifact
# is treated as the authoritative, pinned geometry of I_n (per PRD §4.1), so
# these tests prove the mga render layer contributes no hidden state, no
# cross-page dependence, and no non-determinism.
# ---------------------------------------------------------------------------


class TestRenderPurity:
    """Verify render(P_n) is a pure function of (I_n, T_n) given the artifact."""

    @staticmethod
    def _write_translations_json(stage, payload: Path, ctx, cfg, page_idx: int) -> str:
        """Run the guard and return the raw translations-NNNN.json text."""
        stage._write_page_translations(payload, ctx, cfg, page_idx)
        return (payload / f"translations-{page_idx:04d}.json").read_text(encoding="utf-8")

    def test_output_deterministic_across_instances(self, tmp_path: Path) -> None:
        """Two freshly constructed RenderStage instances, same (I_n, T_n, artifact),
        must produce byte-identical translations JSON. Proves no hidden/persistent
        state leaks between instances (the S2T cache is instance-scoped)."""
        img = _make_text_png(tmp_path / "page.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=0, text_regions=[
            {"index": 0, "text": "x", "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]], "prob": 0.9},
        ])
        ctx = PipelineContext(
            project_config=ProjectConfig(),
            pages=[Page(page_id="p0", page_index=0, image=PageImage(path=str(img)))],
            translations=[TranslationCandidate(bubble_id="region-0000-0000", text="你好")],
        )

        out_a = self._write_translations_json(RenderStage(), tmp_path, ctx, ProjectConfig(), 0)
        # Fresh instance, fresh tmp payload dir, same inputs.
        tmp_b = tmp_path / "b"; tmp_b.mkdir()
        _write_artifact(tmp_b, page_idx=0, text_regions=[
            {"index": 0, "text": "x", "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]], "prob": 0.9},
        ])
        out_b = self._write_translations_json(RenderStage(), tmp_b, ctx, ProjectConfig(), 0)
        assert out_a == out_b  # byte-identical → deterministic, no hidden state

    def test_output_independent_of_other_pages(self, tmp_path: Path) -> None:
        """Page 0's render output must not depend on page 1's translations or
        pages being present in the context — render(P_0) = f(I_0, T_0) only."""
        img = _make_text_png(tmp_path / "page-001.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=0, text_regions=[
            {"index": 0, "text": "x", "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]], "prob": 0.9},
        ])
        page0 = Page(page_id="p0", page_index=0, image=PageImage(path=str(img)))
        t0 = TranslationCandidate(bubble_id="region-0000-0000", text="页面零")

        # Context with ONLY page 0.
        ctx_only = PipelineContext(project_config=ProjectConfig(), pages=[page0], translations=[t0])
        out_only = self._write_translations_json(RenderStage(), tmp_path, ctx_only, ProjectConfig(), 0)

        # Context that ALSO has page 1's translations and a page-1 object.
        # (Reuse tmp; overwrite is fine since we read before re-rendering.)
        tmp2 = tmp_path / "p2"; tmp2.mkdir()
        _write_artifact(tmp2, page_idx=0, text_regions=[
            {"index": 0, "text": "x", "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]], "prob": 0.9},
        ])
        page1 = Page(page_id="p1", page_index=1, image=PageImage(path=str(img)))
        t1 = TranslationCandidate(bubble_id="region-0001-0000", text="页面一干扰")
        ctx_with_other = PipelineContext(
            project_config=ProjectConfig(), pages=[page0, page1], translations=[t0, t1],
        )
        out_with_other = self._write_translations_json(RenderStage(), tmp2, ctx_with_other, ProjectConfig(), 0)
        assert out_only == out_with_other  # page 0 unaffected by page 1's presence

    def test_output_depends_on_translation(self, tmp_path: Path) -> None:
        """Different T_n must yield different output (the function is non-trivial
        in T_n)."""
        img = _make_text_png(tmp_path / "page.png", width=500, height=500)
        _write_artifact(tmp_path, page_idx=0, text_regions=[
            {"index": 0, "text": "x", "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]], "prob": 0.9},
        ])
        page = Page(page_id="p0", page_index=0, image=PageImage(path=str(img)))

        out_a = self._write_translations_json(
            RenderStage(), tmp_path,
            PipelineContext(project_config=ProjectConfig(), pages=[page],
                            translations=[TranslationCandidate(bubble_id="region-0000-0000", text="你好")]),
            ProjectConfig(), 0)

        tmp_b = tmp_path / "b"; tmp_b.mkdir()
        _write_artifact(tmp_b, page_idx=0, text_regions=[
            {"index": 0, "text": "x", "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]], "prob": 0.9},
        ])
        out_b = self._write_translations_json(
            RenderStage(), tmp_b,
            PipelineContext(project_config=ProjectConfig(), pages=[page],
                            translations=[TranslationCandidate(bubble_id="region-0000-0000", text="再见")]),
            ProjectConfig(), 0)
        assert out_a != out_b  # different T_n → different output

    def test_output_depends_on_input_image(self, tmp_path: Path) -> None:
        """Same artifact + T_n, but a different I_n (blank vs. text at the region
        coords) must yield different output: the guard drops the blank-region
        translation. Proves dependence on I_n."""
        blank = _make_white_png(tmp_path / "blank.png", width=500, height=500)
        text_img = _make_text_png(tmp_path / "text.png", width=500, height=500)
        region = [{"index": 0, "text": "x", "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]], "prob": 0.9}]
        t = TranslationCandidate(bubble_id="region-0000-0000", text="测试")

        # Blank I_n → guard drops the region (region lands on white).
        _write_artifact(tmp_path, page_idx=0, text_regions=region)
        ctx_blank = PipelineContext(
            project_config=ProjectConfig(),
            pages=[Page(page_id="p0", page_index=0, image=PageImage(path=str(blank)))],
            translations=[t],
        )
        out_blank = self._write_translations_json(RenderStage(), tmp_path, ctx_blank, ProjectConfig(), 0)

        # Text I_n → guard keeps the region.
        tmp_t = tmp_path / "t"; tmp_t.mkdir()
        _write_artifact(tmp_t, page_idx=0, text_regions=region)
        ctx_text = PipelineContext(
            project_config=ProjectConfig(),
            pages=[Page(page_id="p0", page_index=0, image=PageImage(path=str(text_img)))],
            translations=[t],
        )
        out_text = self._write_translations_json(RenderStage(), tmp_t, ctx_text, ProjectConfig(), 0)
        assert out_blank != out_text  # different I_n → different output

    def test_no_class_level_mutable_state(self) -> None:
        """The S2T converter cache is instance-scoped, not class-level, so a fresh
        RenderStage carries no inherited mutable state."""
        assert not hasattr(RenderStage, "_s2t_converter_cache"), (
            "RenderStage must not hold class-level mutable state — it would leak "
            "across instances/runs and break render purity."
        )
        s = RenderStage()
        assert isinstance(s._s2t_converter_cache, dict)
        assert s._s2t_converter_cache == {}  # fresh instance starts clean

    def test_pinning_makes_artifact_deterministic_across_reruns(self, tmp_path: Path) -> None:
        """With pin_artifacts=True, a re-OCR that overwrites the artifact with
        different content does NOT change the rendered output: the pin restores
        the first-seen artifact for sha256(I_n). This closes the g(I_n) gap —
        runtime OCR non-determinism no longer propagates to the rendered image."""
        img = _make_text_png(tmp_path / "page.png", width=500, height=500)
        page = Page(page_id="p0", page_index=0, image=PageImage(path=str(img)))
        t = TranslationCandidate(bubble_id="region-0000-0000", text="你好")
        # Region on the text band (kept by the guard), prob 0.9.
        region_v1 = [{"index": 0, "text": "x",
                      "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]], "prob": 0.9}]

        # Run 1 (pin ON): pins artifact v1 → output keeps region 0.
        payload = tmp_path / "payload"; payload.mkdir()
        _write_artifact(payload, page_idx=0, text_regions=region_v1)
        ctx = PipelineContext(project_config=ProjectConfig(), pages=[page], translations=[t])
        out1 = self._write_translations_json(
            RenderStage(pin_artifacts=True), payload, ctx, ProjectConfig(), 0)
        assert '"region_index": 0' in out1  # region kept

        # Simulate a fresh non-deterministic Pass-1: overwrite the artifact with a
        # LOW-prob version (would be dropped by the guard without pinning).
        region_v2 = [{"index": 0, "text": "x",
                      "lines": [[[0, 100], [500, 100], [500, 400], [0, 400]]], "prob": 0.10}]
        (payload / "artifact-0000.json").write_text(
            json.dumps({"version": 1, "page_index": 0, "text_regions": region_v2,
                        "render_config": {}, "image_shape": [500, 500, 3]}),
            encoding="utf-8")

        # Run 2 (pin ON, same payload/pin-store): pin restores v1 → output identical.
        out2 = self._write_translations_json(
            RenderStage(pin_artifacts=True), payload, ctx, ProjectConfig(), 0)
        assert out1 == out2  # pinning neutralized the artifact change

        # Control: with pin OFF, the changed (low-prob) artifact WOULD drop the region.
        payload_ctrl = tmp_path / "ctrl"; payload_ctrl.mkdir()
        _write_artifact(payload_ctrl, page_idx=0, text_regions=region_v2)
        out_ctrl = self._write_translations_json(
            RenderStage(pin_artifacts=False), payload_ctrl, ctx, ProjectConfig(), 0)
        assert '"region_index": 0' not in out_ctrl  # dropped without pin
        assert out1 != out_ctrl  # pinning made the difference
