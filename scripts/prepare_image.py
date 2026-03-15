#!/usr/bin/env python3
"""Prepare an image for an RGB LED matrix (rpi-rgb-led-matrix).

Usage:
  python3 scripts/prepare_image.py INPUT.png OUTPUT.png COLS ROWS [--bg '#RRGGBB']

The script scales the input image to fit within (COLS x ROWS) while preserving
aspect ratio, centers it on a background of the requested color, and writes
an RGB PNG sized to the matrix resolution.
"""
from PIL import Image, ImageColor, ImageOps
import sys


def prepare_image(src_path: str, out_path: str, cols: int, rows: int, bg: str = "#000000"):
    img = Image.open(src_path).convert("RGBA")
    target = (cols, rows)

    # Fit the image inside target while preserving aspect ratio
    fitted = ImageOps.contain(img, target, Image.LANCZOS)

    # Compose on background so we have a full RGB image with chosen background color
    bg_color = ImageColor.getrgb(bg)
    out = Image.new("RGB", target, bg_color)
    # Center the fitted image
    x = (cols - fitted.width) // 2
    y = (rows - fitted.height) // 2
    out.paste(fitted.convert("RGB"), (x, y))

    out.save(out_path)
    print(f"Saved prepared image to {out_path} ({cols}x{rows})")


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python3 scripts/prepare_image.py INPUT.png OUTPUT.png COLS ROWS [--bg '#RRGGBB']")
        sys.exit(1)
    src = sys.argv[1]
    out = sys.argv[2]
    cols = int(sys.argv[3])
    rows = int(sys.argv[4])
    bg = "#000000"
    if "--bg" in sys.argv:
        idx = sys.argv.index("--bg")
        if idx + 1 < len(sys.argv):
            bg = sys.argv[idx + 1]
    prepare_image(src, out, cols, rows, bg)
