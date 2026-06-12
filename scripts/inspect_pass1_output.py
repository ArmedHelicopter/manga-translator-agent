#!/usr/bin/env python3
"""Create a 5x2 thumbnail grid for manual inspection of Pass 1 output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAYLOAD_DIR = ROOT / "data" / "experiments" / "pass1-fix-validation" / ".mga-payload"
DEFAULT_GRID_PATH = ROOT / "data" / "experiments" / "pass1-fix-validation" / "inpainted-grid.png"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
try:
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
except AttributeError:
    RESAMPLE_LANCZOS = Image.LANCZOS


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a 5x2 inspection grid from inpainted-*.png files.")
    parser.add_argument(
        "--payload-dir",
        type=Path,
        default=DEFAULT_PAYLOAD_DIR,
        help=f"Payload directory containing inpainted-*.png files. Default: {DEFAULT_PAYLOAD_DIR}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_GRID_PATH,
        help=f"Grid image path. Default: {DEFAULT_GRID_PATH}",
    )
    parser.add_argument("--columns", type=int, default=5, help="Grid columns. Default: 5.")
    parser.add_argument("--rows", type=int, default=2, help="Grid rows. Default: 2.")
    parser.add_argument("--thumb-width", type=int, default=360, help="Thumbnail width in pixels. Default: 360.")
    parser.add_argument("--thumb-height", type=int, default=520, help="Thumbnail height in pixels. Default: 520.")
    return parser.parse_args()


def resolve_rooted(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (ROOT / path).resolve()


def find_inpainted_images(payload_dir: Path) -> list[Path]:
    images = sorted(payload_dir.glob("inpainted-*.png"))
    if images:
        return images
    return sorted(
        path
        for path in payload_dir.rglob("inpainted*.*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS
    )


def load_pages_manifest(payload_dir: Path) -> list[dict[str, object]]:
    pages_path = payload_dir / "pages.json"
    if not pages_path.exists():
        return []
    try:
        pages = json.loads(pages_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return pages if isinstance(pages, list) else []


def make_thumbnail(path: Path, size: tuple[int, int], label: str) -> Image.Image:
    thumb_width, thumb_height = size
    label_height = 34
    canvas = Image.new("RGB", (thumb_width, thumb_height + label_height), "white")

    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((thumb_width, thumb_height), RESAMPLE_LANCZOS)
        x = (thumb_width - image.width) // 2
        y = (thumb_height - image.height) // 2
        canvas.paste(image, (x, y))

    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("arial.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    draw.rectangle((0, thumb_height, thumb_width, thumb_height + label_height), fill=(245, 245, 245))
    draw.text((8, thumb_height + 8), label[:48], fill=(0, 0, 0), font=font)
    return canvas


def build_grid(images: list[Path], output_path: Path, columns: int, rows: int, thumb_size: tuple[int, int]) -> Path:
    if columns < 1 or rows < 1:
        raise ValueError("columns and rows must be positive integers")

    selected = images[: columns * rows]
    if not selected:
        raise ValueError("no inpainted images found")

    thumb_width, thumb_height = thumb_size
    label_height = 34
    gap = 16
    margin = 20
    cell_width = thumb_width
    cell_height = thumb_height + label_height
    grid_width = margin * 2 + columns * cell_width + (columns - 1) * gap
    grid_height = margin * 2 + rows * cell_height + (rows - 1) * gap
    grid = Image.new("RGB", (grid_width, grid_height), (230, 230, 230))

    for index, path in enumerate(selected):
        row = index // columns
        col = index % columns
        label = f"{index + 1}: {path.name}"
        thumbnail = make_thumbnail(path, thumb_size, label)
        x = margin + col * (cell_width + gap)
        y = margin + row * (cell_height + gap)
        grid.paste(thumbnail, (x, y))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    grid.save(output_path)
    return output_path


def main() -> int:
    args = parse_args()
    payload_dir = resolve_rooted(args.payload_dir)
    output_path = resolve_rooted(args.output)

    if not payload_dir.exists():
        print(f"Payload directory does not exist: {payload_dir}", file=sys.stderr)
        return 2

    images = find_inpainted_images(payload_dir)
    if not images:
        print(f"No inpainted output images found under: {payload_dir}", file=sys.stderr)
        return 2

    pages = load_pages_manifest(payload_dir)
    grid_path = build_grid(
        images,
        output_path,
        columns=args.columns,
        rows=args.rows,
        thumb_size=(args.thumb_width, args.thumb_height),
    )

    print(f"Found {len(images)} inpainted image(s):")
    for path in images:
        print(f"  - {path.resolve()}")

    if pages:
        print("Pages manifest entries:")
        for page in pages[: args.columns * args.rows]:
            page_index = page.get("page_index") if isinstance(page, dict) else None
            inpainted = page.get("inpainted") if isinstance(page, dict) else None
            artifact = page.get("artifact") if isinstance(page, dict) else None
            print(f"  - page {page_index}: inpainted={inpainted}, artifact={artifact}")

    print(f"Inspection grid written to: {grid_path.resolve()}")
    print("Open the grid image and the listed inpainted files for manual visual inspection.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
