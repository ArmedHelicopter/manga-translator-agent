"""PDF adapter — extracts pages as PNG images via PyMuPDF (fitz)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterator

from ..models.format import PageRef, TranslatedPage
from .base import FormatAdapter

# Render settings
_RENDER_DPI = 300


def _get_fitz():  # noqa: D401 – lazy import wrapper
    """Return the ``fitz`` module, raising a clear error if unavailable."""
    try:
        import fitz  # PyMuPDF

        return fitz
    except ImportError as exc:
        raise ImportError(
            "PyMuPDF is required for PDF support.  Install it with: pip install PyMuPDF"
        ) from exc


class PDFAdapter(FormatAdapter):
    """Adapter for PDF files.

    Extract renders every page to a temporary PNG at 300 DPI and returns a
    ``PageRef`` for each one.  Repack assembles translated PNGs into a new
    PDF at the same DPI.
    """

    def extract(self, input_path: Path) -> Iterator[PageRef]:
        fitz = _get_fitz()

        if not input_path.is_file():
            raise FileNotFoundError(f"Input path is not a file: {input_path}")

        tmpdir = Path(tempfile.mkdtemp(prefix="mga_pdf_"))

        doc = fitz.open(str(input_path))
        try:
            zoom = _RENDER_DPI / 72.0  # PDF points → pixels
            mat = fitz.Matrix(zoom, zoom)

            for idx in range(doc.page_count):
                page = doc.load_page(idx)
                pix = page.get_pixmap(matrix=mat, alpha=False)
                out = tmpdir / f"page_{idx:04d}.png"
                pix.save(str(out))

                yield PageRef(
                    index=idx,
                    image_path=str(out),
                    original_ref=f"{input_path.name}#page={idx}",
                    metadata={
                        "source_pdf": str(input_path),
                        "page_number": idx,
                        "dpi": _RENDER_DPI,
                    },
                )
        finally:
            doc.close()

    def repack(self, pages: Iterator[TranslatedPage], output_path: Path) -> None:
        fitz = _get_fitz()

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Collect pages and sort by index so the PDF order is correct.
        sorted_pages = sorted(pages, key=lambda p: p.index)
        if not sorted_pages:
            return

        # Use the first image's dimensions for the PDF page size.
        first = fitz.open(sorted_pages[0].image_path)
        page_width = first[0].rect.width
        page_height = first[0].rect.height
        first.close()

        doc = fitz.open()  # new empty PDF
        try:
            for tpage in sorted_pages:
                img_doc = fitz.open(tpage.image_path)
                rect = fitz.Rect(0, 0, page_width, page_height)
                pdf_bytes = img_doc.convert_to_pdf()
                img_doc.close()

                pdf_page_doc = fitz.open("pdf", pdf_bytes)
                page = doc.new_page(width=page_width, height=page_height)
                page.show_pdf_page(rect, pdf_page_doc, 0)
                pdf_page_doc.close()

            doc.save(str(output_path))
        finally:
            doc.close()
