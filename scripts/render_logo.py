#!/usr/bin/env python3
"""Render the logo images in docs/ from the board's own drawing code, so they never drift from it.

  python scripts/render_logo.py

writes docs/logo.png (the README's wordmark: the mark, PELOTON LED and the zone bar) and
docs/screenshots/rotation/logo.png (the startup logo on a 64x64 and a 64x32 panel).
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from display.display import get_text_width, initialize_fonts, loaded_fonts  # noqa: E402
from display.ui.logo_art import LABEL_GREY, MARK_WIDTH, PELOTON_RED, mark_pixels, zone_color  # noqa: E402
from display.ui.logo_mask_screen import WHITE, LogoMaskScreen  # noqa: E402
from driver import graphics  # noqa: E402
from scripts.render_demo import ImageMatrix  # noqa: E402

WORDMARK_SCALE = 4
WORDMARK_BACKGROUND = (11, 13, 18)
PAD = 4
SHEET_BACKGROUND = (27, 27, 27)
SHEET_SCALE = 3
LABEL_WIDTH = 70
GAP = 6


def wordmark():
    """The mark beside PELOTON LED, underlined by the zone bar, each pixel WORDMARK_SCALE wide."""
    initialize_fonts(64)
    big, small = loaded_fonts['discipline'], loaded_fonts['titles']
    words_x = MARK_WIDTH + 4
    led_x = words_x + get_text_width(big, 'PELOTON') + 5
    width = led_x + get_text_width(small, 'LED') + PAD * 2
    matrix = ImageMatrix(width, 30 + PAD * 2)
    for x, y in mark_pixels(PAD, PAD + 1):
        matrix.SetPixel(x, y, *PELOTON_RED)
    graphics.DrawText(matrix, big, PAD + words_x, PAD + 17, graphics.Color(*WHITE), 'PELOTON')
    graphics.DrawText(matrix, small, PAD + led_x, PAD + 17, graphics.Color(*LABEL_GREY), 'LED')
    bar = width - PAD * 2 - words_x
    for i in range(bar):
        for j in range(2):
            matrix.SetPixel(PAD + words_x + i, PAD + 22 + j, *zone_color(i, bar))
    image = Image.new('RGB', matrix.image.size, WORDMARK_BACKGROUND)
    image.paste(matrix.image, mask=matrix.image.convert('L').point(lambda v: 255 if v else 0))
    return image.resize((image.width * WORDMARK_SCALE, image.height * WORDMARK_SCALE), Image.NEAREST)


def startup_sheet():
    """The startup logo on a 64x64 and a 64x32 panel, labelled, like the README's other screenshots."""
    panels = []
    for height in (64, 32):
        initialize_fonts(height)
        matrix = ImageMatrix(64, height)
        LogoMaskScreen().render(matrix)
        panels.append((f'64x{height}', matrix.image.resize((64 * SHEET_SCALE, height * SHEET_SCALE), Image.NEAREST)))
    width = LABEL_WIDTH + 64 * SHEET_SCALE + GAP
    sheet = Image.new('RGB', (width, GAP + sum(p.height + GAP * 2 for _, p in panels) - GAP), SHEET_BACKGROUND)
    draw = ImageDraw.Draw(sheet)
    top = GAP
    for label, panel in panels:
        sheet.paste(panel, (LABEL_WIDTH, top))
        draw.text((GAP, top + panel.height // 2 - 6), label, fill=(200, 200, 200))
        top += panel.height + GAP * 2
    return sheet


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--wordmark', default=os.path.join(ROOT, 'docs', 'logo.png'))
    parser.add_argument('--startup', default=os.path.join(ROOT, 'docs', 'screenshots', 'rotation', 'logo.png'))
    options = parser.parse_args(argv)
    wordmark().save(options.wordmark)
    startup_sheet().save(options.startup)
    print(f'Wrote {options.wordmark} and {options.startup}')


if __name__ == '__main__':
    main()
