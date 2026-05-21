"""Novel MOBI adapter — converts MOBI to EPUB via Calibre, then uses NovelEPUBAdapter."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterator

from ..models.format import PageRef, TranslatedPage
from .base import FormatAdapter
from .novel_epub import NovelEPUBAdapter


class NovelMOBIAdapter(FormatAdapter):
    """Adapter for translating MOBI files.

    Converts MOBI to EPUB via Calibre's ``ebook-convert``, then delegates
    to :class:`NovelEPUBAdapter` for text extraction and repacking.
    Repack output is EPUB (MOBI round-trip is unreliable).
    """

    def __init__(self) -> None:
        self._epub_adapter = NovelEPUBAdapter()

    def extract(self, input_path: Path) -> Iterator[PageRef]:
        if not input_path.is_file():
            raise FileNotFoundError(f"Input path is not a file: {input_path}")

        ebook_convert = shutil.which("ebook-convert")
        if ebook_convert is None:
            raise RuntimeError(
                "Calibre's 'ebook-convert' not found on PATH. "
                "Install Calibre to handle MOBI files."
            )

        tmpdir = Path(tempfile.mkdtemp(prefix="mga_mobi_"))
        tmp_epub = tmpdir / "converted.epub"

        subprocess.run(
            [ebook_convert, str(input_path), str(tmp_epub)],
            check=True,
            capture_output=True,
        )

        if not tmp_epub.exists():
            raise RuntimeError(f"Calibre conversion failed: {tmp_epub}")

        yield from self._epub_adapter.extract(tmp_epub)

    def repack(self, pages: Iterator[TranslatedPage], output_path: Path) -> None:
        """Repack as EPUB (MOBI round-trip is unreliable)."""
        self._epub_adapter.repack(pages, output_path)
