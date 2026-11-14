#!/usr/bin/env python3
"""Render the README's next-milestone screenshot from the board's own drawing code, so it never drifts from it.

  python scripts/render_countdown.py

writes docs/screenshots/rotation/next-milestone.png: the countdown page for each case in PAGES, on a
64x64 panel (top row) and a 64x32 panel (bottom row), labelled like the README's other screenshots.
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from display.display import initialize_fonts  # noqa: E402
from display.ui.countdown_screen import CountdownScreen  # noqa: E402
from scripts.render_demo import ImageMatrix  # noqa: E402
from scripts.render_logo import GAP, LABEL_WIDTH, SHEET_BACKGROUND, SHEET_SCALE  # noqa: E402

# 3 to go, the one-left wording, a discipline, the total, and the three bootcamps (TREAD BOOTCAMP is the widest name).
PAGES = [
    {'total': 597, 'target': 600, 'previous': 500, 'title': 'Cycling', 'discipline': 'cycling'},
    {'total': 599, 'target': 600, 'previous': 500, 'title': 'Cycling', 'discipline': 'cycling'},
    {'total': 496, 'target': 500, 'previous': 400, 'title': 'Strength', 'discipline': 'strength'},
    {'total': 2197, 'target': 2200, 'previous': 2100, 'title': 'Workouts', 'discipline': None},
    {'total': 47, 'target': 50, 'previous': 25, 'title': 'Row Bootcamp', 'discipline': 'row_bootcamp'},
    {'total': 47, 'target': 50, 'previous': 25, 'title': 'Bike Bootcamp', 'discipline': 'bike_bootcamp'},
    {'total': 47, 'target': 50, 'previous': 25, 'title': 'Tread Bootcamp', 'discipline': 'tread_bootcamp'},
]


def panels(height, scale=SHEET_SCALE):
    """Each page in PAGES drawn on a 64 x `height` panel, each pixel `scale` wide."""
    initialize_fonts(height)
    images = []
    for state in PAGES:
        matrix = ImageMatrix(64, height)
        if not CountdownScreen().render(matrix, state):
            raise RuntimeError(f'countdown drew nothing for {state}')
        images.append(matrix.image.resize((64 * scale, height * scale), Image.NEAREST))
    return images


def sheet():
    rows = [(f'64x{height}', panels(height)) for height in (64, 32)]
    width = LABEL_WIDTH + len(PAGES) * (64 * SHEET_SCALE + GAP)
    height = GAP + sum(images[0].height + GAP * 2 for _, images in rows) - GAP
    image = Image.new('RGB', (width, height), SHEET_BACKGROUND)
    draw = ImageDraw.Draw(image)
    top = GAP
    for label, images in rows:
        for index, panel in enumerate(images):
            image.paste(panel, (LABEL_WIDTH + index * (panel.width + GAP), top))
        draw.text((GAP, top + images[0].height // 2 - 6), label, fill=(200, 200, 200))
        top += images[0].height + GAP * 2
    return image


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--out', default=os.path.join(ROOT, 'docs', 'screenshots', 'rotation', 'next-milestone.png'))
    options = parser.parse_args(argv)
    sheet().save(options.out)
    print(f'Wrote {options.out}')


if __name__ == '__main__':
    main()
