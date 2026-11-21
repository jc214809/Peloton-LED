#!/usr/bin/env python3
"""Render the README's Club Peloton screenshot from the board's own drawing code, so it never drifts from it.

  python scripts/render_club.py

writes docs/screenshots/rotation/club.png: the club page for each case in PAGES, on a 64x64 panel (top row)
and a 64x32 panel (bottom row), labelled like the README's other screenshots.
"""
import argparse
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from display.display import initialize_fonts  # noqa: E402
from display.ui.club_screen import ClubScreen  # noqa: E402
from peloton.feeds.club import club_page  # noqa: E402
from scripts.render_demo import ImageMatrix  # noqa: E402
from scripts.render_logo import GAP, LABEL_WIDTH, SHEET_BACKGROUND, SHEET_SCALE  # noqa: E402


def _club(level, points, tier, marks, following, to_next, boost=False):
    return {'level': level, 'points': points, 'tier_min': tier[0], 'tier_max': tier[1], 'marks': marks,
            'next': following, 'to_next': to_next, 'boost_until': 1.0 if boost else None}


# Tiers as Peloton sent them on 2026-11-14: a level just reached, Gold III in a double-points boost,
# Champion (no levels inside its tier), and Legend (the top: no tier above, a full bar).
PAGES = [
    club_page(_club('GOLD I', 2410, (2000, 15000), [4000, 6000], 'GOLD II', 1590), None, 0),
    club_page(_club('GOLD III', 13659, (2000, 15000), [4000, 6000], 'CHAMPION', 1341, boost=True), None, 0),
    club_page(_club('CHAMPION', 15666, (15000, 30000), [], 'LEGEND', 14334), None, 0),
    club_page(_club('LEGEND', 31205, (30000, None), [], None, None), None, 0),
]


def panels(height, scale=SHEET_SCALE):
    """Each page in PAGES drawn on a 64 x `height` panel, each pixel `scale` wide."""
    initialize_fonts(height)
    images = []
    for state in PAGES:
        matrix = ImageMatrix(64, height)
        if not ClubScreen().render(matrix, state):
            raise RuntimeError(f'club page drew nothing for {state}')
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
    parser.add_argument('--out', default=os.path.join(ROOT, 'docs', 'screenshots', 'rotation', 'club.png'))
    options = parser.parse_args(argv)
    sheet().save(options.out)
    print(f'Wrote {options.out}')


if __name__ == '__main__':
    main()
