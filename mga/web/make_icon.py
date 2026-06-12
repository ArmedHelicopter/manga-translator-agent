"""Generate the application icon set from a single rendered source.

Produces:
    web/dist-icons/icon.png   (512x512, used by Linux / pywebview)
    web/dist-icons/icon.ico   (Windows, multi-resolution)
    web/dist-icons/icon.icns  (macOS, if Pillow build supports it)

The icon is a rounded blue square with a white "M", matching the in-app
brand mark. Run with:  python -m mga.web.make_icon
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_OUT_DIR = Path(__file__).resolve().parents[2] / "web" / "dist-icons"
_BG_TOP = (59, 130, 246)      # primary-500
_BG_BOTTOM = (37, 99, 235)    # primary-600
_FG = (255, 255, 255)


def _vertical_gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        ratio = y / max(size - 1, 1)
        grad.putpixel(
            (0, y),
            tuple(int(top[i] + (bottom[i] - top[i]) * ratio) for i in range(3)),
        )
    return grad.resize((size, size))


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Try a few common bold fonts; fall back to PIL's default.
    candidates = [
        "arialbd.ttf",
        "Arial Bold.ttf",
        "DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def render_icon(size: int = 512) -> Image.Image:
    base = _vertical_gradient(size, _BG_TOP, _BG_BOTTOM).convert("RGBA")
    mask = _rounded_mask(size, radius=int(size * 0.22))
    icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    icon.paste(base, (0, 0), mask)

    draw = ImageDraw.Draw(icon)
    font = _load_font(int(size * 0.62))
    text = "M"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pos = ((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1])
    draw.text(pos, text, font=font, fill=_FG)
    return icon


def main() -> None:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    master = render_icon(512)

    png_path = _OUT_DIR / "icon.png"
    master.save(png_path)
    print(f"[icon] wrote {png_path}")

    ico_path = _OUT_DIR / "icon.ico"
    master.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"[icon] wrote {ico_path}")

    icns_path = _OUT_DIR / "icon.icns"
    try:
        master.save(icns_path, format="ICNS")
        print(f"[icon] wrote {icns_path}")
    except (ValueError, OSError) as exc:
        print(f"[icon] skipped .icns ({exc}); PNG/ICO are sufficient on this platform")


if __name__ == "__main__":
    main()
