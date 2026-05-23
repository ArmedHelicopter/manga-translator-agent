"""MOBI adapter — converts MOBI to EPUB via Calibre, then delegates."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterator

from ..models.format import PageRef, TranslatedPage
from .base import FormatAdapter


def _require_calibre() -> None:
    """Raise a clear error if Calibre's ``ebook-convert`` is not available."""
    if shutil.which("ebook-convert") is None:
        raise FileNotFoundError(
            "Calibre's 'ebook-convert' was not found on PATH.  "
            "MOBI support requires Calibre.  Install it from https://calibre-ebook.com/"
        )


class MOBIAdapter(FormatAdapter):
    """Adapter for MOBI files.

    Extraction converts the MOBI to a temporary EPUB using ``ebook-convert``
    (Calibre) and then delegates to :class:`EPUBAdapter` for image
    extraction.

    Repack is not supported directly — the translated images are placed into
    a CBZ-compatible ZIP that can be sideloaded to most e-readers.
    """

    def extract(self, input_path: Path) -> Iterator[PageRef]:
        _require_calibre()

        if not input_path.is_file():
            raise FileNotFoundError(f"Input path is not a file: {input_path}")

        tmpdir = Path(tempfile.mkdtemp(prefix="mga_mobi_"))
        epub_path = tmpdir / "converted.epub"

        try:
            subprocess.run(
                [
                    "ebook-convert",
                    str(input_path),
                    str(epub_path),
                ],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"ebook-convert failed on {input_path}: "
                f"{exc.stderr.decode(errors='replace')}"
            ) from exc

        # Delegate to EPUBAdapter for the actual image extraction.
        from .epub_adapter import EPUBAdapter

        epub_adapter = EPUBAdapter()
        yield from epub_adapter.extract(epub_path)

    def repack(self, pages: Iterator[TranslatedPage], output_path: Path) -> None:
        """Repack as a CBZ (ZIP of images) since MOBI repack is non-trivial."""
        import zipfile

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        sorted_pages = sorted(pages, key=lambda p: p.index)
        if not sorted_pages:
            return

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for tpage in sorted_pages:
                src = Path(tpage.image_path)
                if not src.exists():
                    continue
                zf.write(src, f"{tpage.index:04d}{src.suffix}")
