"""CBZ/CBR adapter — extracts / repacks comic book archives."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
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


def _is_image(name: str) -> bool:
    return Path(name).suffix.lower() in IMAGE_EXTENSIONS


class CBZAdapter(FormatAdapter):
    """Adapter for CBZ (ZIP-based) and CBR (RAR-based) comic archives.

    CBZ files are handled natively via ``zipfile``.  CBR files are extracted
    by invoking ``unrar`` (must be installed and on PATH).
    """

    # ------------------------------------------------------------------
    # Extract
    # ------------------------------------------------------------------

    def extract(self, input_path: Path) -> Iterator[PageRef]:
        if not input_path.is_file():
            raise FileNotFoundError(f"Input path is not a file: {input_path}")

        suffix = input_path.suffix.lower()
        if suffix == ".cbz":
            yield from self._extract_zip(input_path)
        elif suffix == ".cbr":
            yield from self._extract_rar(input_path)
        else:
            raise ValueError(f"Unsupported archive format: {suffix}")

    def _extract_zip(self, input_path: Path) -> Iterator[PageRef]:
        tmpdir = Path(tempfile.mkdtemp(prefix="mga_cbz_"))

        with zipfile.ZipFile(input_path, "r") as zf:
            image_entries = sorted(
                [e for e in zf.infolist() if _is_image(e.filename)],
                key=lambda e: _natural_sort_key(e.filename),
            )
            for idx, entry in enumerate(image_entries):
                extracted = zf.extract(entry, path=tmpdir)
                yield PageRef(
                    index=idx,
                    image_path=extracted,
                    original_ref=entry.filename,
                    metadata={"archive_entry": entry.filename},
                )

    def _extract_rar(self, input_path: Path) -> Iterator[PageRef]:
        tmpdir = Path(tempfile.mkdtemp(prefix="mga_cbr_"))

        try:
            subprocess.run(
                ["unrar", "x", "-o+", "-inul", str(input_path), str(tmpdir)],
                check=True,
                capture_output=True,
            )
        except FileNotFoundError:
            raise FileNotFoundError(
                "The 'unrar' command was not found.  Install it to support CBR files "
                "(e.g. ``sudo apt install unrar``)."
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"unrar failed to extract {input_path}: {exc.stderr.decode(errors='replace')}"
            ) from exc

        # Walk the extracted tree and collect images.
        image_files: list[Path] = []
        for root, _dirs, files in os.walk(tmpdir):
            for f in files:
                if _is_image(f):
                    image_files.append(Path(root) / f)

        image_files.sort(key=lambda p: _natural_sort_key(p.name))
        for idx, img in enumerate(image_files):
            yield PageRef(
                index=idx,
                image_path=str(img),
                original_ref=str(img.relative_to(tmpdir)),
                metadata={"archive_entry": str(img.relative_to(tmpdir))},
            )

    # ------------------------------------------------------------------
    # Repack
    # ------------------------------------------------------------------

    def repack(self, pages: Iterator[TranslatedPage], output_path: Path) -> None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Always repack as CBZ (ZIP), even if the source was CBR.
        sorted_pages = sorted(pages, key=lambda p: p.index)
        if not sorted_pages:
            return

        with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for tpage in sorted_pages:
                src = Path(tpage.image_path)
                if not src.exists():
                    continue
                original_ref = (
                    tpage.page_json.get("archive_entry") if tpage.page_json else None
                )
                arcname = original_ref or f"{tpage.index:04d}{src.suffix}"
                zf.write(src, arcname)
