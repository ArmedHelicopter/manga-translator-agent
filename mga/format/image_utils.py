"""Utilities for creating bilingual side-by-side PDF pages."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _load_image(path: str) -> Image.Image:
    """Load an image from *path*, converting to RGB if needed."""
    img = Image.open(path)
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img


def _get_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a TrueType font, fall back to the default bitmap font."""
    for name in ("DejaVuSans.ttf", "Arial.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def create_bilingual_page(
    original_path: str,
    translated_path: str,
    output_path: str,
    *,
    page_number: int | None = None,
    gap: int = 10,
    bg_color: str = "white",
) -> str:
    """Create a single side-by-side page image.

    The original image is placed on the left and the translated image on
    the right, separated by *gap* pixels.  An optional *page_number* is
    drawn at the bottom centre.

    Returns the path to the written output image.
    """
    orig = _load_image(original_path)
    trans = _load_image(translated_path)

    # Scale both images to the same height for a clean layout.
    target_h = max(orig.height, trans.height)
    if orig.height != target_h:
        ratio = target_h / orig.height
        orig = orig.resize((int(orig.width * ratio), target_h), Image.LANCZOS)
    if trans.height != target_h:
        ratio = target_h / trans.height
        trans = trans.resize((int(trans.width * ratio), target_h), Image.LANCZOS)

    total_w = orig.width + gap + trans.width
    total_h = target_h

    # Reserve space at the bottom for a page-number label.
    label_h = 0
    if page_number is not None:
        label_h = 30

    canvas = Image.new("RGB", (total_w, total_h + label_h), bg_color)
    canvas.paste(orig, (0, 0))
    canvas.paste(trans, (orig.width + gap, 0))

    if page_number is not None:
        draw = ImageDraw.Draw(canvas)
        font = _get_font(18)
        label = f"Page {page_number}"
        bbox = draw.textbbox((0, 0), label, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((total_w - tw) / 2, target_h + 4), label, fill="black", font=font)

    canvas.save(output_path)
    return output_path


def merge_bilingual_pages(page_paths: list[str], output_path: str) -> str:
    """Merge a list of side-by-side page images into a single PDF.

    Each element in *page_paths* should be the path to an image file.
    The first image becomes page 1, and so on.

    Returns the path to the written PDF.
    """
    if not page_paths:
        raise ValueError("page_paths must not be empty")

    images = [_load_image(p) for p in page_paths]
    first, rest = images[0], images[1:]
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    first.save(str(out), "PDF", save_all=True, append_images=rest)
    return str(out)
