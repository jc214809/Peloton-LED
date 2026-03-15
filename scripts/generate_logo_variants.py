#!/usr/bin/env python3
"""Generate optimized logo variants for target LED matrix sizes.

This script takes a source image (preferably high-resolution or SVG-rasterized)
and produces multiple candidate PNGs for each target resolution. The
candidates use different resizing and processing strategies (nearest for
pixel-perfect, LANCZOS with unsharp, color quantization, posterize, and
monochrome dithering) so you can A/B test them on your matrix.

Usage:
  python3 scripts/generate_logo_variants.py SOURCE.png --out-dir prepared_logos

Optional flags:
  --sizes 64x32,64x64    comma-separated target sizes
  --colors 12            number of colors for quantized variants

Output files are written to OUT_DIR and named like:
  prepared_64x32_nearest.png
  prepared_64x32_lanczos_sharp.png
  prepared_64x32_quant12.png

"""
from PIL import Image, ImageFilter, ImageOps
import argparse
import os

VARIANTS = [
    "nearest",
    "lanczos_sharp",
    "lanczos_unsharp",
    "quant",
    "posterize",
    "mono_dither",
]


def make_nearest(img, size):
    return img.resize(size, Image.NEAREST).convert("RGB")


def make_lanczos_sharp(img, size):
    out = img.resize(size, Image.LANCZOS).convert("RGB")
    out = out.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
    return out


def make_lanczos_unsharp(img, size):
    out = img.resize(size, Image.LANCZOS).convert("RGB")
    out = out.filter(ImageFilter.UnsharpMask(radius=0.8, percent=120, threshold=1))
    return out


def make_quant(img, size, colors=12):
    out = img.resize(size, Image.LANCZOS).convert("RGB")
    # Quantize to a reduced palette
    return out.quantize(colors=colors, method=Image.MEDIANCUT)


def make_posterize(img, size, bits=6):
    out = img.resize(size, Image.LANCZOS).convert("RGB")
    # Posterize reduces number of bits per channel
    return ImageOps.posterize(out, bits)


def make_mono_dither(img, size):
    out = img.resize(size, Image.LANCZOS).convert("L")
    return out.convert("1")


def ensure_out_dir(path: str):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)


def parse_size(s: str):
    try:
        w, h = s.lower().split("x")
        return (int(w), int(h))
    except Exception:
        raise argparse.ArgumentTypeError(f"Invalid size: {s}; expected WIDTHxHEIGHT")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source", help="Source image (high-res PNG or rasterized SVG)")
    p.add_argument("--out-dir", default="prepared_logos", help="Output directory")
    p.add_argument("--sizes", default="64x32,64x64", help="Comma-separated sizes, e.g. 64x32,64x64")
    p.add_argument("--colors", type=int, default=12, help="Colors for quantized variant")
    args = p.parse_args()

    sizes = [parse_size(s.strip()) for s in args.sizes.split(",") if s.strip()]
    ensure_out_dir(args.out_dir)

    src = Image.open(args.source).convert("RGBA")

    for size in sizes:
        w, h = size
        print(f"Generating variants for {w}x{h}...")
        # Start from a contained image (keeps aspect ratio)
        contained = ImageOps.contain(src, (w, h), Image.LANCZOS)
        # Create background canvas and center the contained image
        bg = Image.new("RGBA", (w, h), (0, 0, 0, 255))
        x = (w - contained.width) // 2
        y = (h - contained.height) // 2
        bg.paste(contained, (x, y), contained)

        # Nearest
        nn = make_nearest(bg, (w, h))
        nn.save(os.path.join(args.out_dir, f"prepared_{w}x{h}_nearest.png"))

        # Lanczos + strong unsharp
        ls = make_lanczos_sharp(bg, (w, h))
        ls.save(os.path.join(args.out_dir, f"prepared_{w}x{h}_lanczos_sharp.png"))

        # Lanczos + lighter unsharp
        lu = make_lanczos_unsharp(bg, (w, h))
        lu.save(os.path.join(args.out_dir, f"prepared_{w}x{h}_lanczos_unsharp.png"))

        # Quantized
        q = make_quant(bg, (w, h), colors=args.colors)
        # quantize returns 'P' mode, convert to RGB for display viewers that expect RGB PNGs
        q.convert("RGB").save(os.path.join(args.out_dir, f"prepared_{w}x{h}_quant{args.colors}.png"))

        # Posterize
        pimg = make_posterize(bg, (w, h), bits=6)
        pimg.save(os.path.join(args.out_dir, f"prepared_{w}x{h}_posterize6.png"))

        # Mono dither (1-bit)
        mono = make_mono_dither(bg, (w, h))
        mono.save(os.path.join(args.out_dir, f"prepared_{w}x{h}_mono_dither.png"))

    print(f"Variants written to {args.out_dir}")


if __name__ == "__main__":
    main()
