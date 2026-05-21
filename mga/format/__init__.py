"""Format adapters for input/output processing."""

from __future__ import annotations

from .base import FormatAdapter
from .cbz_adapter import CBZAdapter
from .epub_adapter import EPUBAdapter
from .images import ImageDirAdapter
from .manifest import build_manifest_payload, discover_image_paths, load_image_metadata
from .mobi_adapter import MOBIAdapter
from .pdf_adapter import PDFAdapter

__all__ = [
    "FormatAdapter",
    "ImageDirAdapter",
    "PDFAdapter",
    "EPUBAdapter",
    "CBZAdapter",
    "MOBIAdapter",
    "build_manifest_payload",
    "discover_image_paths",
    "load_image_metadata",
    "get_adapter",
]

# ------------------------------------------------------------------
# Factory
# ------------------------------------------------------------------

# Maps lowercase format name (without dot) → adapter class.
_ADAPTER_REGISTRY: dict[str, type[FormatAdapter]] = {
    "images": ImageDirAdapter,
    "pdf": PDFAdapter,
    "epub": EPUBAdapter,
    "cbz": CBZAdapter,
    "cbr": CBZAdapter,
    "mobi": MOBIAdapter,
}


def get_adapter(format_name: str) -> FormatAdapter:
    """Return a :class:`FormatAdapter` instance for *format_name*.

    *format_name* is matched case-insensitively and should not include a
    leading dot (e.g. ``"pdf"`` not ``".pdf"``).

    Raises ``ValueError`` if the format is not supported.
    """
    key = format_name.lstrip(".").lower()
    cls = _ADAPTER_REGISTRY.get(key)
    if cls is None:
        supported = ", ".join(sorted(_ADAPTER_REGISTRY.keys()))
        raise ValueError(
            f"Unknown format {format_name!r}.  Supported formats: {supported}"
        )
    return cls()
