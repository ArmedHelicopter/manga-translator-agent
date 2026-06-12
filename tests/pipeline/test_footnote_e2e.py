"""E2E test for footnote rendering pipeline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from mga.models import Bubble, Page, PageImage, ProjectConfig, TranslationCandidate
from mga.models.page import PageFootnote
from mga.models.translation import FootnoteEntry
from mga.pipeline.page_footnotes import PageFootnoteService


def create_synthetic_manga_page(output_path: Path, page_num: int, text: str) -> Path:
    """Create a simple manga page image with Japanese text."""
    img = Image.new("RGB", (800, 1200), color="white")
    draw = ImageDraw.Draw(img)

    # Draw simple speech bubble box
    draw.rectangle([100, 200, 700, 400], outline="black", width=2)

    # Draw text (PIL default font, no fancy Japanese rendering needed for test)
    draw.text((150, 280), text, fill="black")

    page_path = output_path / f"page_{page_num:03d}.png"
    img.save(page_path)
    return page_path


def test_footnote_e2e_pipeline(tmp_path):
    """E2E test: synthetic manga → footnote compilation → JSON validation."""

    # Setup directories
    input_dir = tmp_path / "input"
    input_dir.mkdir()

    # Test data: 10 pages with Japanese text including katakana loanwords and cultural terms
    test_pages = [
        ("ハイボールを一杯", ["ハイボール"]),  # highball (cultural)
        ("コーヒーはいかが？", ["コーヒー"]),  # coffee (loanword)
        ("お嬢様、召し上がれ", ["お嬢様"]),  # cultural term
        ("居酒屋で飲もう", ["居酒屋"]),  # izakaya (cultural)
        ("アバターを作る", ["アバター"]),  # avatar (fictional/game)
        ("神社に行く", ["神社"]),  # shrine (cultural)
        ("スキルを使う", ["スキル"]),  # skill (fictional/game)
        ("お守りを買う", ["お守り"]),  # amulet (cultural)
        ("レベルアップ！", ["レベル"]),  # level (fictional/game)
        ("浴衣を着る", ["浴衣"]),  # yukata (cultural)
    ]

    pages = []
    for i, (text, expected_terms) in enumerate(test_pages, start=1):
        img_path = create_synthetic_manga_page(input_dir, i, text)

        bubble = Bubble(
            bubble_id=f"b{i:03d}",
            source_text=text,
            reading_order=0,
        )

        page = Page(
            page_id=f"p{i:03d}",
            page_index=i - 1,
            image=PageImage(path=str(img_path), width=800, height=1200),
            bubbles=[bubble],
            source_text=text,
        )
        pages.append((page, expected_terms))

    # Simulate translation stage output with footnotes
    service = PageFootnoteService()

    for page, expected_terms in pages:
        bubble = page.bubbles[0]

        # Create translation with footnotes
        footnotes = []
        for term in expected_terms:
            footnotes.append(FootnoteEntry(
                original=term,
                translation="translated_term",
                type="cultural" if term in ["ハイボール", "お嬢様", "居酒屋", "神社", "お守り", "浴衣"] else "loanword",
                explanation=None,  # Let service generate
            ))

        translation = TranslationCandidate(
            bubble_id=bubble.bubble_id,
            text="Translated text",
            rationale="test",
            confidence=0.9,
            footnotes=footnotes,
        )

        # Compile page footnotes
        page_footnotes = service.compile_page_footnotes(
            bubbles=[bubble],
            translations=[translation],
            page_context=page.source_text,
        )

        page.page_footnotes = page_footnotes

    # Write output JSON files (simulating pipeline output)
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    for page, _ in pages:
        json_path = output_dir / f"translations-{page.page_id}.json"
        json_path.write_text(
            json.dumps({
                "page_id": page.page_id,
                "bubbles": [b.model_dump() for b in page.bubbles],
                "footnotes": [f.model_dump() for f in page.page_footnotes],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # Validation phase
    all_footnotes = []
    for json_file in sorted(output_dir.glob("translations-*.json")):
        data = json.loads(json_file.read_text(encoding="utf-8"))

        # Check footnotes array exists
        assert "footnotes" in data, f"Missing footnotes in {json_file.name}"

        footnotes = data["footnotes"]
        assert isinstance(footnotes, list), f"Footnotes not a list in {json_file.name}"

        if footnotes:
            all_footnotes.extend(footnotes)

            # Check footnote structure
            for fn in footnotes:
                assert "term" in fn, f"Missing term in {json_file.name}"
                assert "explanation" in fn, f"Missing explanation in {json_file.name}"
                assert "type" in fn, f"Missing type in {json_file.name}"
                assert fn["explanation"], f"Empty explanation in {json_file.name}"

    # Verify we got footnotes
    assert len(all_footnotes) == 10, f"Expected 10 footnotes, got {len(all_footnotes)}"

    # Check for specific terms
    terms = {fn["term"] for fn in all_footnotes}
    assert "ハイボール" in terms, "Missing highball term"
    assert "コーヒー" in terms, "Missing coffee term"
    assert "お嬢様" in terms, "Missing ojou-sama term"

    # Verify no duplicate terms (deduplication working)
    assert len(terms) == len(all_footnotes), "Duplicate footnotes found"

    # Check explanations are present and non-trivial
    for fn in all_footnotes:
        assert len(fn["explanation"]) > 5, f"Trivial explanation for {fn['term']}"


def test_footnote_deduplication(tmp_path):
    """Test that duplicate terms within a page are deduplicated."""
    service = PageFootnoteService()

    bubbles = [
        Bubble(bubble_id="b1", source_text="ハイボールを飲む"),
        Bubble(bubble_id="b2", source_text="もう一杯ハイボール"),
    ]

    translations = [
        TranslationCandidate(
            bubble_id="b1",
            text="Drink a highball",
            rationale="test",
            confidence=0.9,
            footnotes=[FootnoteEntry(original="ハイボール", translation="highball", type="cultural")],
        ),
        TranslationCandidate(
            bubble_id="b2",
            text="One more highball",
            rationale="test",
            confidence=0.9,
            footnotes=[FootnoteEntry(original="ハイボール", translation="highball", type="cultural")],
        ),
    ]

    page_footnotes = service.compile_page_footnotes(bubbles, translations)

    # Should only have one footnote despite two occurrences
    assert len(page_footnotes) == 1
    assert page_footnotes[0].term == "ハイボール"
    assert page_footnotes[0].explanation  # Should have explanation


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
