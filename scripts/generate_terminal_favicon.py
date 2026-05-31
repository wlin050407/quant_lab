"""Generate rounded favicons matching BrandMark (26.5% radius, white tile)."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw

BRAND_RADIUS_RATIO = 0.265
SRC_NAME = "quantlab-icon.png"


def _repo_web_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "src" / "quant_lab" / "terminal" / "web"


def rounded_brand_icon(src: Path, size: int) -> Image.Image:
    """White rounded tile + logo, same proportions as ``BrandMark``."""
    icon = Image.open(src).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
    radius = max(4, round(size * BRAND_RADIUS_RATIO))

    out = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    out.paste(icon, (0, 0), icon)

    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    out.putalpha(mask)

    px = out.load()
    for y in range(size):
        for x in range(size):
            if mask.getpixel((x, y)) == 0:
                px[x, y] = (0, 0, 0, 0)

    return out


def generate_favicons(
    *,
    src: Path | None = None,
    out_dir: Path | None = None,
) -> list[Path]:
    web = _repo_web_dir()
    src_path = src or (web / "src" / "assets" / "brand" / SRC_NAME)
    public = out_dir or (web / "public")
    if not src_path.is_file():
        raise FileNotFoundError(f"missing brand icon: {src_path}")

    public.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    png_128 = rounded_brand_icon(src_path, 128)
    png_path = public / "favicon.png"
    png_128.save(png_path, format="PNG", optimize=True)
    written.append(png_path)

    touch = rounded_brand_icon(src_path, 180)
    touch_path = public / "apple-touch-icon.png"
    touch.save(touch_path, format="PNG", optimize=True)
    written.append(touch_path)

    ico_sizes = [16, 32, 48, 64]
    ico_images = [rounded_brand_icon(src_path, s) for s in ico_sizes]
    ico_path = public / "favicon.ico"
    ico_images[0].save(
        ico_path,
        format="ICO",
        sizes=[(s, s) for s in ico_sizes],
        append_images=ico_images[1:],
    )
    written.append(ico_path)

    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args(argv)

    paths = generate_favicons(src=args.src, out_dir=args.out_dir)
    for p in paths:
        print(f"wrote {p}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
