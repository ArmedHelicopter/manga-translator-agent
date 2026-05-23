"""Bilingual PDF output — original text on left, translation on right."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def create_bilingual_pdf(
    pages: list[Any],
    translations: list[Any],
    output_path: str | Path,
    title: str = "Bilingual Translation",
) -> Path:
    """Create a bilingual PDF with original and translated text side by side.

    For each page, creates a spread:
    - Left page: original Japanese text
    - Right page: translated text (Simplified Chinese)

    Args:
        pages: List of Page objects with source text.
        translations: List of TranslationCandidate objects.
        output_path: Path to the output PDF.
        title: Document title.

    Returns:
        Path to the created PDF.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    # Build translation lookup
    trans_by_id = {t.bubble_id: t for t in translations}

    # Try reportlab first, fall back to text-based PDF
    try:
        return _create_pdf_with_reportlab(pages, trans_by_id, output, title)
    except ImportError:
        logger.info("reportlab not available, using fallback PDF generation")
        return _create_fallback_pdf(pages, trans_by_id, output, title)


def _create_pdf_with_reportlab(
    pages: list[Any],
    trans_by_id: dict[str, Any],
    output: Path,
    title: str,
) -> Path:
    """Create PDF using reportlab."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT, TA_RIGHT

    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=15*mm,
        rightMargin=15*mm,
        topMargin=15*mm,
        bottomMargin=15*mm,
    )

    styles = getSampleStyleSheet()
    jp_style = ParagraphStyle(
        'Japanese',
        parent=styles['Normal'],
        fontSize=11,
        leading=16,
        alignment=TA_LEFT,
    )
    zh_style = ParagraphStyle(
        'Chinese',
        parent=styles['Normal'],
        fontSize=11,
        leading=16,
        alignment=TA_LEFT,
    )
    title_style = ParagraphStyle(
        'Title',
        parent=styles['Title'],
        fontSize=16,
        spaceAfter=12,
    )

    story = []

    # Title page
    story.append(Paragraph(title, title_style))
    story.append(Spacer(1, 20*mm))
    story.append(Paragraph(f"共 {len(pages)} 页", styles['Normal']))
    story.append(PageBreak())

    # Bilingual spreads
    for page in pages:
        page_id = getattr(page, "page_id", f"page_{page.page_index}")

        # Collect bubbles sorted by reading order
        bubbles = sorted(page.bubbles, key=lambda b: getattr(b, 'reading_order', 0))

        if not bubbles:
            continue

        # Page header
        story.append(Paragraph(f"页面 {page.page_index + 1} ({page_id})", styles['Heading2']))
        story.append(Spacer(1, 5*mm))

        # Build table: Japanese | Chinese
        table_data = [[
            Paragraph("<b>原文 (Japanese)</b>", styles['Normal']),
            Paragraph("<b>译文 (Chinese)</b>", styles['Normal']),
        ]]

        for bubble in bubbles:
            source = getattr(bubble, 'source_text', '')
            candidate = trans_by_id.get(getattr(bubble, 'bubble_id', ''))
            translated = candidate.text if candidate else ""

            table_data.append([
                Paragraph(_escape_xml(source), jp_style),
                Paragraph(_escape_xml(translated), zh_style),
            ])

        table = Table(table_data, colWidths=[85*mm, 85*mm])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.9)),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.97, 0.97, 0.97)]),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
        story.append(PageBreak())

    doc.build(story)
    logger.info("Created bilingual PDF: %s (%d pages)", output, len(pages))
    return output


def _create_fallback_pdf(
    pages: list[Any],
    trans_by_id: dict[str, Any],
    output: Path,
    title: str,
) -> Path:
    """Fallback PDF generation without reportlab — creates a simple text file."""
    # When reportlab is not available, create a formatted text file
    text_path = output.with_suffix(".txt")

    lines = [f"{'='*60}", title, f"共 {len(pages)} 页", f"{'='*60}", ""]

    for page in pages:
        page_id = getattr(page, "page_id", f"page_{page.page_index}")
        lines.append(f"--- 页面 {page.page_index + 1} ({page_id}) ---")
        lines.append("")

        bubbles = sorted(page.bubbles, key=lambda b: getattr(b, 'reading_order', 0))
        for bubble in bubbles:
            source = getattr(bubble, 'source_text', '')
            candidate = trans_by_id.get(getattr(bubble, 'bubble_id', ''))
            translated = candidate.text if candidate else ""

            lines.append(f"原文: {source}")
            lines.append(f"译文: {translated}")
            lines.append("")

        lines.append("")

    text_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Created fallback bilingual text: %s", text_path)
    return text_path


def _escape_xml(text: str) -> str:
    """Escape XML special characters for reportlab Paragraph."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
