#!/usr/bin/env python3
"""Render the README's milestone-celebration screenshot from the board's own drawing code, so it never drifts from it.

  python scripts/render_celebration.py

writes docs/screenshots/rotation/milestones.png: the celebration at each time in FRAME_SECONDS (the trophy
rising, then the text), on a 64x64 panel (top row) and a 64x32 panel (bottom row), labelled like the README's
other screenshots.
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from display.display import initialize_fonts  # noqa: E402
from display.ui.celebration_screen import CelebrationScreen  # noqa: E402
from scripts.render_demo import ImageMatrix  # noqa: E402
from scripts.render_logo import GAP, LABEL_WIDTH, SHEET_BACKGROUND, SHEET_SCALE  # noqa: E402

STATE = {'number': 2000, 'noun': 'WORKOUT', 'subtitle': 'Jen'}
# Three frames of the trophy rising through the confetti, then three of the card.
FRAME_SECONDS = [0.1, 0.3, 0.5, 1.2, 2.4, 3.6]


def panels(height, scale=SHEET_SCALE):
    """The celebration at each of FRAME_SECONDS on a 64 x `height` panel, each pixel `scale` wide."""
    initialize_fonts(height)
    images = []
    for seconds in FRAME_SECONDS:
        matrix = ImageMatrix(64, height)
        screen = CelebrationScreen()
        screen.on_enter(matrix, STATE)
        screen.update(seconds)
        screen.render(matrix, STATE)
        images.append(matrix.image.resize((64 * scale, height * scale), Image.NEAREST))
    return images


def sheet():
    rows = [(f'64x{height}', panels(height)) for height in (64, 32)]
    width = LABEL_WIDTH + len(FRAME_SECONDS) * (64 * SHEET_SCALE + GAP)
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
    parser.add_argument('--out', default=os.path.join(ROOT, 'docs', 'screenshots', 'rotation', 'milestones.png'))
    options = parser.parse_args(argv)
    sheet().save(options.out)
    print(f'Wrote {options.out}')


if __name__ == '__main__':
    main()
