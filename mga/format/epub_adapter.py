"""EPUB adapter — extracts / repacks images from EPUB archives (zipfile)."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Iterator

from ..models.format import PageRef, TranslatedPage
from .base import FormatAdapter
from .manifest import IMAGE_EXTENSIONS


def _natural_sort_key(name: str):
    """Return a sort key that handles embedded numbers naturally."""
    parts = re.split(r"(\d+)", name)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


class EPUBAdapter(FormatAdapter):
    """Adapter for EPUB files.

    An EPUB is a ZIP archive.  We locate image entries inside it, extract
    them to a temporary directory, and yield a ``PageRef`` for each.

    Repack copies translated images back into a ZIP structure with the
    ``.epub`` extension.
    """

    @staticmethod
    def _is_image(name: str) -> bool:
        return Path(name).suffix.lower() in IMAGE_EXTENSIONS

    def extract(self, input_path: Path) -> Iterator[PageRef]:
        if not input_path.is_file():
            raise FileNotFoundError(f"Input path is not a file: {input_path}")

        tmpdir = Path(tempfile.mkdtemp(prefix="mga_epub_"))

        with zipfile.ZipFile(input_path, "r") as zf:
            # Collect image entries and sort them naturally.
            image_entries = sorted(
                [e for e in zf.infolist() if self._is_image(e.filename)],
                key=lambda e: _natural_sort_key(e.filename),
            )

            for idx, entry in enumerate(image_entries):
                extracted = zf.extract(entry, path=tmpdir)
                yield PageRef(
                    index=idx,
                    image_path=extracted,
                    original_ref=entry.filename,
                    metadata={
                        "epub_entry": entry.filename,
                        "epub_idx": idx,
                    },
                )

    def repack(self, pages: Iterator[TranslatedPage], output_path: Path) -> None:
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
                # Preserve the original EPUB-relative name when available.
                original_ref = tpage.page_json.get("epub_entry") if tpage.page_json else None
                arcname = original_ref or f"images/{tpage.index:04d}{src.suffix}"
                zf.write(src, arcname)
