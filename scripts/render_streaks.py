#!/usr/bin/env python3
"""Render the README's streak screenshots from the board's own drawing code, so they never drift from it.

  python scripts/render_streaks.py

writes docs/screenshots/rotation/streaks.png (the weekly and the daily streak) and streak-risk.png (the weekend
reminder), each on a 64x64 panel (top row) and a 64x32 panel (bottom row), labelled like the README's other
screenshots. The flame is drawn FLAME_SECONDS into the page.
"""

import argparse
import os
import sys

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from display.display import initialize_fonts  # noqa: E402
from display.ui.streak_risk_screen import StreakRiskScreen  # noqa: E402
from display.ui.streak_screen import StreakScreen  # noqa: E402
from scripts.render_demo import ImageMatrix  # noqa: E402
from scripts.render_logo import GAP, LABEL_WIDTH, SHEET_BACKGROUND, SHEET_SCALE  # noqa: E402

# A moment with all three tongues up, so the screenshot shows the flame's shape.
FLAME_SECONDS = 7.95
SHEETS = {
    'streaks.png': (
        StreakScreen,
        [
            {'current_weekly': 103, 'best_weekly': 103, 'view': 'weekly'},
            {
                'current_weekly': 103,
                'best_weekly': 103,
                'current_daily': 703,
                'daily_start': '2024-12-08',
                'today': '2026-11-02',
                'view': 'daily',
            },
        ],
    ),
    'streak-risk.png': (StreakRiskScreen, [{'current': 1, 'days_left': 1}]),
}


def panels(screen_class, states, height, scale=SHEET_SCALE):
    """Each of `states` drawn by `screen_class` on a 64 x `height` panel, each pixel `scale` wide."""
    initialize_fonts(height)
    images = []
    for state in states:
        matrix = ImageMatrix(64, height)
        screen = screen_class()
        screen.on_enter(matrix, state)
        screen.update(FLAME_SECONDS)
        if not screen.render(matrix, state):
            raise RuntimeError(f'{screen_class.__name__} drew nothing for {state}')
        images.append(matrix.image.resize((64 * scale, height * scale), Image.NEAREST))
    return images


def sheet(screen_class, states):
    rows = [(f'64x{height}', panels(screen_class, states, height)) for height in (64, 32)]
    width = LABEL_WIDTH + len(states) * (64 * SHEET_SCALE + GAP)
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
    parser.add_argument('--out-dir', default=os.path.join(ROOT, 'docs', 'screenshots', 'rotation'))
    options = parser.parse_args(argv)
    for name, (screen_class, states) in SHEETS.items():
        path = os.path.join(options.out_dir, name)
        sheet(screen_class, states).save(path)
        print(f'Wrote {path}')


if __name__ == '__main__':
    main()
