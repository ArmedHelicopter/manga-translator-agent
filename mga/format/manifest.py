"""Manifest and image discovery utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional, Tuple

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}


def discover_image_paths(directory: Path) -> List[Path]:
    """Discover sorted image file paths in a directory."""

    directory = Path(directory)
    if not directory.is_dir():
        return []

    paths = [
        p for p in sorted(directory.iterdir())
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    ]
    return paths


def load_image_metadata(path: Path) -> Tuple[int, int, Optional[int]]:
    """Load image width, height, and DPI from a file.

    Returns (width, height, dpi) where dpi may be None.
    """
    try:
        from PIL import Image

        with Image.open(path) as img:
            width, height = img.size
            dpi_info = img.info.get("dpi")
            dpi = int(dpi_info[0]) if dpi_info else None
            return width, height, dpi
    except Exception:
        return 0, 0, None


def build_manifest_payload(
    project_name: str,
    input_dir: Path,
    pages: list,
) -> dict[str, Any]:
    """Build the manifest payload for a translation run."""

    return {
        "project_name": project_name,
        "input_dir": str(Path(input_dir).resolve()),
        "page_count": len(pages),
        "pages": [
            {
                "page_id": getattr(page, "page_id", ""),
                "page_index": getattr(page, "page_index", idx),
                "image_path": getattr(page.image, "path", "") if hasattr(page, "image") else "",
            }
            for idx, page in enumerate(pages)
        ],
    }
