#!/usr/bin/env python3
"""Render the README's lifetime screenshot from the board's own drawing code, so it never drifts from it.

  python scripts/render_lifetime.py

writes docs/screenshots/rotation/lifetime.png: the lifetime pages for TOTALS (biggest first), four tiles a
page on a 64x64 panel (top row) and two on a 64x32 panel (bottom row), labelled like the README's other
screenshots.
"""

import argparse
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from display.display import initialize_fonts  # noqa: E402
from display.ui.lifetime_overview import LifetimeOverviewScreen  # noqa: E402
from scripts.render_demo import ImageMatrix  # noqa: E402
from scripts.render_logo import GAP, LABEL_WIDTH, SHEET_BACKGROUND, SHEET_SCALE  # noqa: E402

# A real rider's totals, biggest first, the order the board shows them.
TOTALS = [
    ('cycling', 664),
    ('strength', 484),
    ('walking', 426),
    ('stretching', 195),
    ('running', 156),
    ('tread_bootcamp', 116),
    ('bike_bootcamp', 47),
    ('cardio', 41),
    ('meditation', 29),
    ('rowing', 18),
    ('row_bootcamp', 8),
    ('yoga', 4),
]


def panels(height, scale=SHEET_SCALE):
    """Every lifetime page for TOTALS on a 64 x `height` panel, each pixel `scale` wide."""
    initialize_fonts(height)
    per_page = 4 if height >= 64 else 2
    pages = [TOTALS[i : i + per_page] for i in range(0, len(TOTALS), per_page)]
    images = []
    for number, page in enumerate(pages, 1):
        matrix = ImageMatrix(64, height)
        state = {'items': [{'icon': key, 'count': count} for key, count in page], 'page': number, 'pages': len(pages)}
        if not LifetimeOverviewScreen().render(matrix, state):
            raise RuntimeError(f'lifetime page drew nothing for {page}')
        images.append(matrix.image.resize((64 * scale, height * scale), Image.NEAREST))
    return images


def sheet():
    rows = [(f'64x{height}', panels(height)) for height in (64, 32)]
    width = LABEL_WIDTH + max(len(images) for _, images in rows) * (64 * SHEET_SCALE + GAP)
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
    parser.add_argument('--out', default=os.path.join(ROOT, 'docs', 'screenshots', 'rotation', 'lifetime.png'))
    options = parser.parse_args(argv)
    sheet().save(options.out)
    print(f'Wrote {options.out}')


if __name__ == '__main__':
    main()
