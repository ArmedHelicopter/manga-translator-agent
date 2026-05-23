"""Bilingual output adapter — side-by-side original + translated PDF."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Iterator

from ..models.format import PageRef, TranslatedPage
from .base import FormatAdapter
from .image_utils import create_bilingual_page, merge_bilingual_pages
from .manifest import discover_image_paths


class BilingualAdapter(FormatAdapter):
    """Adapter that produces a bilingual side-by-side PDF.

    ``extract()`` works exactly like ``ImageDirAdapter`` — it discovers
    image files in the input directory and yields a ``PageRef`` per image.

    ``repack()`` accepts translated pages whose ``image_path`` points to
    translated images and pairs them with the original images referenced
    via ``PageRef.original_ref`` (stored in ``TranslatedPage.page_json``
    under the ``"original_image_path"`` key).  The result is a PDF where
    each leaf shows the original page on the left and the translated page
    on the right.
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

    def repack(
        self,
        pages: Iterator[TranslatedPage],
        output_path: Path,
        *,
        originals_dir: str | Path | None = None,
    ) -> None:
        """Build a bilingual PDF from translated pages.

        Parameters
        ----------
        pages:
            Iterator of ``TranslatedPage`` instances.  Each must have
            ``page_json["original_image_path"]`` pointing to the
            corresponding original image, and ``image_path`` pointing to
            the translated image.
        output_path:
            Destination path for the output PDF.
        originals_dir:
            Optional fallback directory.  If a translated page lacks an
            explicit ``original_image_path`` in its ``page_json``, the
            adapter looks for ``page_{index:04d}.*`` in this directory.
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        sorted_pages = sorted(pages, key=lambda p: p.index)
        if not sorted_pages:
            return

        tmpdir = Path(tempfile.mkdtemp(prefix="mga_bilingual_"))
        bilingual_images: list[str] = []

        for tpage in sorted_pages:
            translated_img = Path(tpage.image_path)
            if not translated_img.exists():
                continue

            original_img = self._resolve_original(tpage, originals_dir)
            if original_img is None or not original_img.exists():
                continue

            out_img = tmpdir / f"bilingual_{tpage.index:04d}.png"
            create_bilingual_page(
                str(original_img),
                str(translated_img),
                str(out_img),
                page_number=tpage.index + 1,
            )
            bilingual_images.append(str(out_img))

        if bilingual_images:
            merge_bilingual_pages(bilingual_images, str(output_path))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_original(
        tpage: TranslatedPage,
        originals_dir: str | Path | None,
    ) -> Path | None:
        """Resolve the original image path for a translated page."""
        # 1. Explicit path in page_json (preferred).
        if tpage.page_json and "original_image_path" in tpage.page_json:
            return Path(tpage.page_json["original_image_path"])

        # 2. Fallback: look in originals_dir by index.
        if originals_dir is not None:
            base = Path(originals_dir)
            for ext in (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"):
                candidate = base / f"page_{tpage.index:04d}{ext}"
                if candidate.exists():
                    return candidate

        return None
