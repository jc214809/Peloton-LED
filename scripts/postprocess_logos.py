#!/usr/bin/env python3
"""Post-process generated PNGs for LED matrices.

Usage:
  python3 scripts/postprocess_logos.py

This script expects prepared_logos/peloton_64x64.png and
prepared_logos/peloton_64x32.png to exist (created by rasterize_svg.sh).
It writes tuned variants (nearest, sharpened, quantized) into prepared_logos
for quick A/B testing on real hardware.
"""
from PIL import Image, ImageFilter, ImageOps
import os

OUT = 'prepared_logos'

os.makedirs(OUT, exist_ok=True)

src64 = os.path.join(OUT, 'peloton_64x64.png')
src32 = os.path.join(OUT, 'peloton_64x32.png')

if os.path.exists(src64):
    img = Image.open(src64).convert('RGBA')
    # Nearest (pixel-perfect)
    img.save(os.path.join(OUT, 'peloton_64x64_nearest.png'))
    # Sharpened
    im_s = img.resize((64,64), Image.LANCZOS).convert('RGB')
    im_s = im_s.filter(ImageFilter.UnsharpMask(radius=0.8, percent=140, threshold=2))
    im_s.save(os.path.join(OUT, 'peloton_64x64_sharp.png'))
    # Quantized
    q = im_s.quantize(colors=12, method=Image.MEDIANCUT)
    q.convert('RGB').save(os.path.join(OUT, 'peloton_64x64_quant12.png'))
else:
    print(f"Missing {src64}; run scripts/rasterize_svg.sh first")

if os.path.exists(src32):
    img = Image.open(src32).convert('RGBA')
    # For small height, nearest resizing often keeps edges
    img_nearest = img.resize((64,32), Image.NEAREST).convert('RGB')
    img_nearest.save(os.path.join(OUT, 'peloton_64x32_nearest.png'))
    # Lanczos + light sharpen
    im_s = img.resize((64,32), Image.LANCZOS).convert('RGB')
    im_s = im_s.filter(ImageFilter.UnsharpMask(radius=0.5, percent=120, threshold=1))
    im_s.save(os.path.join(OUT, 'peloton_64x32_sharp.png'))
    # Posterize (reduce banding/noise)
    pimg = ImageOps.posterize(im_s, 6)
    pimg.save(os.path.join(OUT, 'peloton_64x32_posterize6.png'))
else:
    print(f"Missing {src32}; run scripts/rasterize_svg.sh first")

print('Postprocessing complete. Compare variants in prepared_logos/')
