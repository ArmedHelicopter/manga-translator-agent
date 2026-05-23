"""Image directory adapter — extracts/ repacks plain image files."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Iterator

from ..models.format import PageRef, TranslatedPage
from .base import FormatAdapter
from .manifest import discover_image_paths


class ImageDirAdapter(FormatAdapter):
    """Adapter for a directory of images.

    Extract discovers image files in the input directory using the shared
    ``discover_image_paths`` helper.  Repack copies translated images to
    *output_path* (creating the directory if needed).
    """

    def extract(self, input_path: Path) -> Iterator[PageRef]:
        if not input_path.is_dir():
            raise FileNotFoundError(f"Input path is not a directory: {input_path}")

        for idx, img in enumerate(discover_image_paths(input_path)):
            yield PageRef(
                index=idx,
                image_path=str(img),
                original_ref=img.name,
                metadata={"filename": img.name, "extension": img.suffix.lower()},
            )

    def repack(self, pages: Iterator[TranslatedPage], output_path: Path) -> None:
        output_path = Path(output_path)
        output_path.mkdir(parents=True, exist_ok=True)

        for page in pages:
            src = Path(page.image_path)
            if not src.exists():
                continue
            # Use zero-padded index for sort-friendly filenames.
            dest = output_path / f"{page.index:04d}{src.suffix}"
            shutil.copy2(src, dest)
