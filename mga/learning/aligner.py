"""Stage L1 — Align original and translated pages by filename matching."""

from __future__ import annotations
from pathlib import Path

from .models import PagePair


# Supported image extensions for manga mode
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}

# Supported text extensions for novel mode
_TEXT_EXTS = {".txt", ".xhtml", ".html", ".epub"}


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
        pairs.append(PagePair(
            original_path=str(orig_path),
            translated_path=str(trans_files[name]),
            page_id=page_id,
        ))

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
        pairs.append(PagePair(
            original_path=str(orig_path),
            translated_path=str(trans_files[name]),
            page_id=page_id,
        ))

    return pairs
