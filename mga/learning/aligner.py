"""Stage L1 — Align original and translated pages by filename matching."""

from __future__ import annotations
from pathlib import Path
import struct

from .models import PagePair


# Supported image extensions for manga mode
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# Supported text extensions for novel mode
_TEXT_EXTS = {".txt", ".xhtml", ".html", ".epub"}


def _image_dimensions(path: Path) -> tuple[int, int] | None:
    data = path.read_bytes()
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return struct.unpack(">II", data[16:24])
    if data.startswith(b"\xff\xd8"):
        idx = 2
        while idx + 9 < len(data):
            if data[idx] != 0xFF:
                idx += 1
                continue
            marker = data[idx + 1]
            idx += 2
            if marker in {0xD8, 0xD9}:
                continue
            if idx + 2 > len(data):
                break
            segment_len = int.from_bytes(data[idx:idx + 2], "big")
            if segment_len < 2:
                break
            if marker in range(0xC0, 0xC4) or marker in range(0xC5, 0xC8) or marker in range(0xC9, 0xCC) or marker in range(0xCD, 0xD0):
                if idx + 7 <= len(data):
                    height = int.from_bytes(data[idx + 3:idx + 5], "big")
                    width = int.from_bytes(data[idx + 5:idx + 7], "big")
                    return width, height
                break
            idx += segment_len
    return None


def _alignment_metadata(original_path: Path, translated_path: Path, ext: str) -> tuple[str, float]:
    if ext not in _IMAGE_EXTS:
        return "filename-only", 0.0
    try:
        original_dims = _image_dimensions(original_path)
        translated_dims = _image_dimensions(translated_path)
    except OSError:
        return "filename-only", 0.0
    if not original_dims or not translated_dims:
        return "filename-only", 0.0
    if original_dims == translated_dims:
        return "visual-verified", 1.0
    return "visual-warning", 0.5


def _make_page_pair(original_path: Path, translated_path: Path, page_id: str, ext: str) -> PagePair:
    status, score = _alignment_metadata(original_path, translated_path, ext)
    return PagePair(
        original_path=str(original_path),
        translated_path=str(translated_path),
        page_id=page_id,
        alignment_status=status,
        alignment_score=score,
    )


def align(project_dir: Path, learn_dir: str | Path) -> list[PagePair]:
    """Pair originals with translations by matching filenames.

    Expected structure under learn_dir:
        originals/   — source pages (images or text)
        translations/ — translated pages (same filenames)

    For novel mode, files are .txt (original) ↔ .txt (translated).
    For manga mode, files are .png (original) ↔ .png (translated).
    """
    learn_path = Path(learn_dir)
    orig_dir = learn_path / "originals"
    trans_dir = learn_path / "translations"

    if not orig_dir.is_dir():
        raise FileNotFoundError(f"Originals directory not found: {orig_dir}")
    if not trans_dir.is_dir():
        raise FileNotFoundError(f"Translations directory not found: {trans_dir}")

    # Determine mode from file extensions
    orig_files = {f.name: f for f in orig_dir.iterdir() if f.is_file()}
    trans_files = {f.name: f for f in trans_dir.iterdir() if f.is_file()}

    # Find matching filenames
    pairs: list[PagePair] = []
    for name, orig_path in sorted(orig_files.items()):
        if name not in trans_files:
            continue
        ext = Path(name).suffix.lower()
        # Validate extension matches expected set (either image or text)
        if ext not in _IMAGE_EXTS and ext not in _TEXT_EXTS:
            continue
        # Generate page_id from filename without extension
        page_id = Path(name).stem
        pairs.append(_make_page_pair(orig_path, trans_files[name], page_id, ext))

    return pairs


def align_from_flat_dirs(orig_dir: Path, trans_dir: Path) -> list[PagePair]:
    """Pair originals with translations from explicitly provided directories."""
    orig_files = {f.name: f for f in orig_dir.iterdir() if f.is_file()}
    trans_files = {f.name: f for f in trans_dir.iterdir() if f.is_file()}

    pairs: list[PagePair] = []
    for name, orig_path in sorted(orig_files.items()):
        if name not in trans_files:
            continue
        ext = Path(name).suffix.lower()
        if ext not in _IMAGE_EXTS and ext not in _TEXT_EXTS:
            continue
        page_id = Path(name).stem
        pairs.append(_make_page_pair(orig_path, trans_files[name], page_id, ext))

    return pairs
